# -*- coding: utf-8 -*-
"""
系统设备识别接口

作用：把「本机现在认到了哪些摄像头、哪些串口」直接告诉前端，
      省去用户自己开设备管理器 / 敲命令去排查。

为什么用 PowerShell 而不是 Python 库：
    Windows 上枚举 PnP 设备最准的就是 Get-PnpDevice，它给出的
    正是设备管理器里显示的那份清单。Python 侧没有等价的轻量接口。

安全边界：
    1. 只读取设备列表，不打开串口、不发送任何指令。
       打开串口会拉 DTR，可能让单片机复位（机械臂可能突然动一下），
       所以「测试串口」这种有副作用的动作不放在自动扫描里。
    2. PowerShell 脚本是写死的常量，不接受任何用户输入拼接，无注入面。
    3. 结果缓存 20 秒，避免用户连点刷新把服务器拖慢。
"""

import json
import platform
import re
import socket
import subprocess
import sys
import time
import urllib.request
from datetime import datetime

from flask import Blueprint, jsonify, request

from extensions import db
from models import SavedDevice
from utils.security import admin_required, login_required, sanitize_text, write_operation_log

system_bp = Blueprint("system", __name__)

# 20 秒缓存：设备插拔的实时性够用，又不至于每次刷新都起一个 PowerShell
_CACHE = {"at": 0.0, "data": None}
_CACHE_TTL = 20

# 只读取，不做任何写操作
#
# 为什么用 Get-CimInstance 而不是 Get-PnpDevice（实测对比）：
#   拿同一台机器测四种写法，结果如下——
#     三次 Get-PnpDevice -Class（各起一遍枚举）      13.9 秒
#     Get-PnpDevice -Class 多类 + PresentOnly         5.8 秒
#     Get-CimInstance 全量再 Where 过滤               4.2 秒
#     Get-CimInstance + WQL 过滤（本方案）            4.0 秒
#   Get-PnpDevice 每查一个类都要刷一遍设备树，串口类尤其慢；
#   改成一次 CIM 查询、在 WQL 里按 PNPClass 过滤，能省掉大部分重复枚举。
#   4 秒仍不算快，所以前端那个请求的超时要单独放宽到 60 秒。
_PS_SCRIPT = r"""
$ErrorActionPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$all = @(Get-CimInstance Win32_PnPEntity -Filter "PNPClass='Camera' OR PNPClass='Image' OR PNPClass='Ports'")
$cams = @($all | Where-Object { $_.PNPClass -eq 'Camera' } | ForEach-Object {
  @{ name = "$($_.Name)"; instance = "$($_.PNPDeviceID)"; status = "$($_.Status)" } })
$imgs = @($all | Where-Object { $_.PNPClass -eq 'Image' } | ForEach-Object {
  @{ name = "$($_.Name)"; instance = "$($_.PNPDeviceID)"; status = "$($_.Status)" } })
$ports = @($all | Where-Object { $_.PNPClass -eq 'Ports' } | ForEach-Object {
  @{ name = "$($_.Name)"; instance = "$($_.PNPDeviceID)"; status = "$($_.Status)" } })
@{ cameras = $cams; images = $imgs; ports = $ports } | ConvertTo-Json -Depth 4 -Compress
"""

# 常见 USB 转串口芯片 → 给人看的解释
_CHIP_HINTS = [
    ("CH340", "CH340", "单片机 / Arduino / 机械臂控制板常见"),
    ("CH341", "CH341", "单片机 / 开发板常见"),
    ("CP210", "CP210x", "ESP32 / 单片机开发板常见"),
    ("FT232", "FT232", "FTDI 通用串口芯片"),
    ("PL2303", "PL2303", "老式 USB 转串口"),
    ("OpenMV", "OpenMV", "OpenMV 摄像头板（正是本项目用的板子）"),
    ("Pyboard", "Pyboard", "MicroPython 开发板"),
    ("ESP32", "ESP32", "ESP32 系列开发板"),
]


def _as_list(value):
    """ConvertTo-Json 在只有一个元素时会把数组压成对象，这里统一成列表。"""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    return []


def _run_powershell(script, timeout=40):
    """
    执行只读的 PowerShell 脚本，返回 (成功?, stdout, 错误说明)。

    超时给到 40 秒：设备枚举实测 4 秒左右，但机器忙、刚开机或插拔设备时
    会明显变慢，留足余量，免得扫描被中途掐断后返回一个空列表。
    """
    if platform.system() != "Windows":
        return False, "", "设备识别目前只支持 Windows 主机"

    try:
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except FileNotFoundError:
        return False, "", "找不到 powershell.exe"
    except subprocess.TimeoutExpired:
        return False, "", "设备查询超时，请稍后重试"

    if proc.returncode != 0 and not proc.stdout.strip():
        return False, "", (proc.stderr or "PowerShell 执行失败").strip()[:200]
    return True, proc.stdout, ""


def _classify_port(name):
    """给串口设备补一句人话解释，便于判断它是不是机械臂/板子。"""
    upper = name.upper()
    for key, label, hint in _CHIP_HINTS:
        if key.upper() in upper:
            return label, hint
    if "蓝牙" in name or "BLUETOOTH" in upper:
        return "蓝牙串口", "手机/耳机等蓝牙设备虚拟出的串口，与分拣无关"
    return "", ""


def _scan():
    """执行一次扫描，返回结构化结果。"""
    ok, stdout, err = _run_powershell(_PS_SCRIPT)
    if not ok:
        return {
            "ok": False,
            "error": err,
            "cameras": [],
            "ports": [],
            "scanned_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "tips": ["设备查询失败：" + err],
        }

    try:
        raw = json.loads(stdout or "{}")
    except json.JSONDecodeError:
        return {
            "ok": False,
            "error": "返回内容解析失败",
            "cameras": [],
            "ports": [],
            "scanned_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "tips": ["设备查询结果无法解析，可能是 PowerShell 输出异常"],
        }

    cameras = []
    for item in _as_list(raw.get("cameras")) + _as_list(raw.get("images")):
        name = (item.get("name") or "").strip()
        if not name:
            continue
        cameras.append({
            "name": name,
            "status": (item.get("status") or "").strip() or "Unknown",
            "instance": (item.get("instance") or "").strip(),
            "builtin_guess": "内置" in name or "HD UVC WebCam" in name,
        })

    ports = []
    for item in _as_list(raw.get("ports")):
        name = (item.get("name") or "").strip()
        if not name:
            continue
        m = re.search(r"(COM\d+)", name, re.IGNORECASE)
        chip, hint = _classify_port(name)
        ports.append({
            "name": name,
            "port": m.group(1).upper() if m else "",
            "status": (item.get("status") or "").strip() or "Unknown",
            "instance": (item.get("instance") or "").strip(),
            "chip": chip,
            "hint": hint,
        })

    # 端口按 COM 号排序，看起来更像设备管理器
    ports.sort(key=lambda p: (p["port"] == "", p["port"]))

    tips = _make_tips(cameras, ports)
    return {
        "ok": True,
        "error": "",
        "cameras": cameras,
        "ports": ports,
        "scanned_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "tips": tips,
    }


def _make_tips(cameras, ports):
    """根据扫描结果生成「下一步该干什么」的提示，前端直接展示。"""
    tips = []
    live_cams = [c for c in cameras if c["status"].upper() == "OK"]

    if not live_cams:
        tips.append("没有识别到任何摄像头。检查 USB 数据线（不是充电线）并确认设备已上电。")
    elif len(live_cams) == 1 and live_cams[0].get("builtin_guess"):
        tips.append(
            "只识别到内置摄像头（%s）。外接摄像头若看不到，通常是数据线、供电或未被系统加载驱动。"
            % live_cams[0]["name"]
        )

    board_ports = [p for p in ports if p["chip"] and "蓝牙" not in p["chip"]]
    if board_ports:
        names = "、".join("%s (%s)" % (p["port"] or p["name"], p["chip"]) for p in board_ports)
        tips.append("检测到 USB 转串口设备：%s，很可能就是控制板/开发板的调试口。" % names)
    elif not ports:
        tips.append("没有识别到串口设备。机械臂的板子可能没插线或没上电。")

    tips.append("扫描只读设备列表，不会打开串口，因此不会让机械臂动作。")
    return tips


def _scan_cached(force=False):
    """扫描设备（带 20 秒缓存）。扫描接口和「连接设备」共用，避免重复起 PowerShell。"""
    now = time.time()
    cached = _CACHE["data"]
    if not force and cached and (now - _CACHE["at"]) < _CACHE_TTL:
        return cached, True

    result = _scan()
    result["host"] = {
        "name": socket.gethostname(),
        "os": platform.system() + " " + platform.release(),
        "python": sys.version.split()[0],
    }
    _CACHE["at"] = now
    _CACHE["data"] = result
    return result, False


@system_bp.get("/devices")
@login_required
def list_devices():
    """扫描本机摄像头与串口。带 20 秒缓存，force=true 可强制重扫。"""
    force = (request.args.get("force") or "").lower() in ("1", "true", "yes")
    result, cached = _scan_cached(force=force)
    payload = dict(result)
    payload["cached"] = cached
    return jsonify(code=0, msg="ok", data=payload)


# ======================= 设备探测 =======================

def _probe(dev_type, target):
    """
    判定一个设备现在能不能用，返回 (是否可用, 人话说明)。

    刻意不做的事：不打开串口。
    打开串口会拉低 DTR，不少单片机会因此复位，机械臂可能突然动一下。
    所以串口这里只核对「端口是否存在、驱动状态是否 OK」，
    真正的通信留给采集脚本在用户明确触发时去做。
    """
    dev_type = (dev_type or "").strip()
    target = (target or "").strip()
    if not target:
        return False, "没有填写要连接的目标"

    if dev_type == "camera":
        return _probe_camera(target)
    if dev_type == "serial":
        return _probe_serial(target)
    if dev_type == "stream":
        return _probe_stream(target)
    return False, "不认识的设备类型：%s" % (dev_type or "(空)")


def _probe_camera(target):
    data, _ = _scan_cached()
    cams = data.get("cameras") or []
    live = [c for c in cams if c.get("status", "").upper() == "OK"]

    if not cams:
        return False, "系统里一个摄像头都没识别到，先检查数据线和供电"

    # 目标写的是序号（采集脚本用的 --index）
    if target.isdigit():
        index = int(target)
        if index < len(live):
            return True, "序号 %d 对应已识别的「%s」；能否取流请用采集脚本实际确认" % (
                index, live[index]["name"])
        return False, "序号 %d 超出范围：当前只识别到 %d 个摄像头" % (index, len(live))

    # 目标写的是设备名
    for c in live:
        if target in c["name"] or c["name"] in target:
            return True, "已识别到「%s」，状态正常" % c["name"]
    return False, "没找到名为「%s」的摄像头，可能在设备管理器里换了名字" % target


def _probe_serial(target):
    port = target.upper().strip()
    if not re.fullmatch(r"COM\d+", port):
        return False, "端口号应该长成 COM3 这样，实际填的是「%s」" % target

    data, _ = _scan_cached()
    for p in data.get("ports") or []:
        if (p.get("port") or "").upper() == port:
            if p.get("status", "").upper() == "OK":
                return True, "端口 %s 存在且驱动正常（未打开串口，不会让板子复位）" % port
            return False, "端口 %s 存在，但状态是 %s，通常是没上电或驱动异常" % (port, p.get("status"))
    return False, "系统里没有 %s 这个端口，检查线插没插、驱动装没装" % port


def _probe_stream(target):
    url = target.strip()
    if not url.lower().startswith(("http://", "https://")):
        return False, "网络流地址要以 http:// 或 https:// 开头"

    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=4) as resp:
            chunk = resp.read(200)
            status = resp.status
            ctype = resp.headers.get("Content-Type", "")
    except Exception as e:
        return False, "连不上：%s" % str(e)[:120]

    if not chunk:
        return False, "地址能打开，但没读到画面数据（HTTP %s）" % status
    return True, "可以连上：HTTP %s，Content-Type=%s，首包 %d 字节" % (
        status, ctype or "(空)", len(chunk))


# ======================= 我的设备（类似 WiFi 的「已保存网络」）=======================

_DEV_TYPES = ("camera", "serial", "stream")


@system_bp.get("/saved")
@login_required
def list_saved():
    """已保存的设备列表。"""
    items = SavedDevice.query.order_by(SavedDevice.id.asc()).all()
    return jsonify(code=0, msg="ok", data={"items": [d.to_dict() for d in items]})


@system_bp.post("/saved")
@admin_required
def create_saved():
    """新增设备：保存后立刻探测一次，把结果写回记录。"""
    body = request.get_json(silent=True) or {}
    dev_type = (body.get("dev_type") or "").strip()
    target = sanitize_text(body.get("target"), 100).strip()
    name = sanitize_text(body.get("name"), 30).strip()
    note = sanitize_text(body.get("note"), 60).strip()
    auto_connect = bool(body.get("auto_connect", True))

    if dev_type not in _DEV_TYPES:
        return jsonify(code=400, msg="设备类型只能是 camera / serial / stream"), 400
    if not target:
        return jsonify(code=400, msg="请填写设备目标"), 400
    if not name:
        name = target

    exists = SavedDevice.query.filter_by(dev_type=dev_type, target=target).first()
    if exists:
        return jsonify(code=400, msg="这个设备已经在列表里了"), 400

    dev = SavedDevice(
        name=name, dev_type=dev_type, target=target, note=note, auto_connect=auto_connect
    )
    db.session.add(dev)
    db.session.flush()

    ok, message = _probe(dev_type, target)
    dev.last_status = "ok" if ok else "fail"
    dev.last_message = message[:200]
    dev.last_connect_time = datetime.now()

    write_operation_log("新增设备", target=target, detail="类型 %s" % dev_type)
    db.session.commit()

    return jsonify(code=0, msg="已添加", data={
        "item": dev.to_dict(),
        "probe": {"ok": ok, "message": message},
    }), 201


@system_bp.delete("/saved/<int:dev_id>")
@admin_required
def delete_saved(dev_id):
    """删除已保存的设备。只删记录，不会动系统里的驱动或设备。"""
    dev = db.session.get(SavedDevice, dev_id)
    if dev is None:
        return jsonify(code=404, msg="设备不存在或已被删除"), 404

    write_operation_log("删除设备", target=dev.target, detail=dev.name)
    db.session.delete(dev)
    db.session.commit()
    return jsonify(code=0, msg="已删除")


@system_bp.post("/saved/<int:dev_id>/connect")
@admin_required
def connect_saved(dev_id):
    """连接已保存的设备：重新探测一次并刷新状态。"""
    dev = db.session.get(SavedDevice, dev_id)
    if dev is None:
        return jsonify(code=404, msg="设备不存在或已被删除"), 404

    ok, message = _probe(dev.dev_type, dev.target)
    dev.last_status = "ok" if ok else "fail"
    dev.last_message = message[:200]
    dev.last_connect_time = datetime.now()
    db.session.commit()

    return jsonify(code=0, msg="连接成功" if ok else "连接失败", data={
        "item": dev.to_dict(),
        "probe": {"ok": ok, "message": message},
    })


@system_bp.patch("/saved/<int:dev_id>")
@admin_required
def update_saved(dev_id):
    """目前只支持切换「自动连接」开关。"""
    dev = db.session.get(SavedDevice, dev_id)
    if dev is None:
        return jsonify(code=404, msg="设备不存在或已被删除"), 404

    body = request.get_json(silent=True) or {}
    if "auto_connect" in body:
        dev.auto_connect = bool(body.get("auto_connect"))
    db.session.commit()
    return jsonify(code=0, msg="ok", data={"item": dev.to_dict()})


@system_bp.post("/probe")
@login_required
def probe_unknown():
    """探测「未知设备」：只测试能不能连，不写库。前端的小窗用这个。"""
    body = request.get_json(silent=True) or {}
    ok, message = _probe(body.get("dev_type"), body.get("target"))
    return jsonify(code=0, msg="ok", data={"ok": ok, "message": message})
