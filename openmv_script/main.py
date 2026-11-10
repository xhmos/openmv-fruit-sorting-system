# -*- coding: utf-8 -*-
"""
================================================================================
基于 OpenMV 的果实智能分拣 —— 板端采集与上报脚本
================================================================================
文件位置：C:\\Users\\10149\\Desktop\\openMV\\openmv_script\\main.py
运行环境：OpenMV IDE（MicroPython 固件），型号 H7 / H7 Plus / RT1062 通用

它做的事：
    1. 摄像头取图，按 LAB 颜色阈值找果实色块
    2. 取面积最大的色块，按「面积区间 + 填充率」判定 good / bad
    3. 在图上画出标记框和文字（这张图就是上传给后端的「标记图」）
    4. 通过 WiFi 用 multipart 表单 POST 到 /api/device/report（带图）
    5. 每隔一段时间上传当前画面到 /api/device/frame，供网页 MJPEG 看板实时播放
    6. 每 10 秒从 /api/setting/device 拉一次阈值参数，网页改完自动生效

联网方式（NET_MODE）三选一：
    "wlan"  —— OpenMV 官方 WiFi 扩展板（WINC1500），用 network.WLAN 直接联网【推荐】
    "esp32" —— OpenMV 通过 UART 把识别结果发给外接 ESP32，由 ESP32 负责联网上报
    "none"  —— 不联网，只在 IDE 里看识别效果，用来调阈值

⚠ 关于阈值的说明（重要，别踩坑）：
    后端 sys_setting 存的是 HSL（色相/饱和度/亮度），OpenMV 的 find_blobs 只吃 LAB。
    两套色彩体系不能直接互换，所以本脚本的颜色阈值写在 FRUITS 里（LAB），
    必须用 OpenMV IDE 的「工具 -> 机器视觉 -> 阈值编辑器」对着真实果实取。
    服务端拉下来的参数里，只有 min_area 会被真正用上（覆盖最小面积），
    HSL 六项会打印在串口日志里，方便你对照着微调 LAB 阈值。
================================================================================
"""

import sensor
import image
import time
import os
import socket

try:
    import ujson as json          # MicroPython 自带，优先用
except ImportError:
    import json                   # 部分固件只有标准 json


# ==============================================================================
# 一、必须改的配置：网络与服务器
# ==============================================================================
NET_MODE = "wlan"                       # "wlan" / "esp32" / "none"

WIFI_SSID = "你的WiFi名"                 # 改成板子要连的 WiFi 名称
WIFI_PASSWORD = "你的WiFi密码"           # 改成对应密码

SERVER_HOST = "10.153.180.220"          # 后端所在电脑的局域网 IPv4（本机 WLAN 地址）
SERVER_PORT = 5000                      # Flask 端口
DEVICE_TOKEN = "openmv-device-2026"     # 必须和 backend/.env 里的 DEVICE_TOKEN 一致

# esp32 模式用的串口（OpenMV H7 的 UART3 一般接扩展板的 TX/RX）
ESP32_UART_ID = 3
ESP32_UART_BAUD = 115200


# ==============================================================================
# 二、识别配置：LAB 颜色阈值（每个品种一组）
# ==============================================================================
# 阈值格式 (L Min, L Max, A Min, A Max, B Min, B Max)，取值范围 L:0~100，A/B:-128~127
# 下面三组只是「能跑起来」的示例值，真实效果必须用阈值编辑器在实物上重新取，否则会误识别
FRUITS = [
    {"name": "apple",  "threshold": (20, 95, 25, 127, 5, 70)},     # 红苹果
    {"name": "orange", "threshold": (45, 100, -5, 55, 45, 127)},   # 橙子
    {"name": "banana", "threshold": (65, 100, -25, 20, 45, 127)},  # 香蕉
]

MIN_AREA = 300          # 最小像素面积，低于它当作噪声（会被服务端 min_area 覆盖）
GOOD_AREA_MIN = 800     # 合格果实的面积下限（太小说明没拍到整颗，判不合格）
GOOD_AREA_MAX = 60000   # 合格果实的面积上限（太大说明整片背景都被算进去）
FILL_RATIO_MIN = 0.45   # 色块填充率下限：实际像素 / 外接矩形面积，越接近 1 形状越规整

# ==============================================================================
# 三、节奏配置
# ==============================================================================
FRAME_INTERVAL_MS = 800         # 实时帧上传间隔（网页 MJPEG 靠它更新，1 秒约 1~2 帧）
SETTING_PULL_MS = 10000         # 参数拉取间隔
REPORT_COOLDOWN_MS = 2500       # 同一颗果实最短重复上报间隔，防止一颗果连报几十条
LOOP_IDLE_MS = 20               # 每轮空转睡眠，别把 CPU 跑满


# ==============================================================================
# 四、全局状态
# ==============================================================================
_state = {
    "network_ready": False,
    "server_min_area": MIN_AREA,
    "server_hsl": {},
    "last_report_ms": 0,
    "last_frame_ms": 0,
    "last_pull_ms": 0,
    "ok_count": 0,
    "fail_count": 0,
}

_uart = None


# ==============================================================================
# 五、基础工具
# ==============================================================================
def log(msg):
    """统一日志出口：串口/IDE 里能直接看到，方便现场调试。"""
    print("[openmv] %s" % msg)


def ticks_now():
    """MicroPython 的毫秒计时，回绕安全，不要换成 time.time()。"""
    return time.ticks_ms()


def elapsed(start_ms):
    """距 start_ms 过去了多少毫秒。"""
    return time.ticks_diff(ticks_now(), start_ms)


def http_status_line(response_bytes):
    """把 'HTTP/1.1 200 OK\\r\\n...' 的第一行剥出来，只用来判断成败。"""
    if not response_bytes:
        return ""
    first = response_bytes.split(b"\r\n", 1)[0]
    try:
        return first.decode()
    except Exception:
        return ""


def json_body(response_bytes):
    """取出响应里 \\r\\n\\r\\n 之后的正文并解析成 dict，解析失败返回空字典。"""
    if not response_bytes:
        return {}
    parts = response_bytes.split(b"\r\n\r\n", 1)
    if len(parts) != 2:
        return {}
    text = parts[1]
    try:
        return json.loads(text)
    except Exception:
        # 有的服务器会用 chunked 编码，正文里带长度前缀，宽松兜底一次
        try:
            start = text.index(b"{")
            end = text.rindex(b"}") + 1
            return json.loads(text[start:end])
        except Exception:
            return {}


# ==============================================================================
# 六、图片编码：拿到一帧的 JPEG 字节
# ==============================================================================
def capture_jpeg(img_obj, quality=70):
    """
    把 image 对象编码成 JPEG 字节，失败返回 None（没有图也能只传数据，后端允许 img_path 为空）。
    优先写 /ram（内存盘），不行再试 SD 卡，最后试当前目录，覆盖「插没插 SD 卡」两种情况。
    """
    candidates = ("/ram/up_tmp.jpg", "/sd/up_tmp.jpg", "up_tmp.jpg")

    for path in candidates:
        try:
            try:
                img_obj.save(path, quality=quality)     # 多数固件支持 quality 关键字
            except Exception:
                img_obj.compress(quality=quality)       # 不支持就直接压缩再存
                img_obj.save(path)
        except Exception:
            continue

        try:
            with open(path, "rb") as f:
                data = f.read()
        except Exception:
            data = None

        try:
            os.remove(path)                             # 立刻删掉，别把存储写满
        except Exception:
            pass

        if data:
            return data

    return None


# ==============================================================================
# 七、HTTP：手写最小实现（不依赖 urequests，避免固件里没这个库）
# ==============================================================================
def http_request(method, path, headers=None, body=None, timeout=8):
    """
    发一个 HTTP/1.1 请求并返回原始响应字节。
    只支持「一次发完、一次收完」，对上报这种小请求足够。
    """
    if not _state["network_ready"]:
        return b""

    headers = headers or []

    try:
        addr = (SERVER_HOST, SERVER_PORT)
        try:
            addr = socket.getaddrinfo(SERVER_HOST, SERVER_PORT)[0][-1]   # 填的是域名时走这里
        except Exception:
            pass                                                          # 填的是 IP 就用原样

        s = socket.socket()
        s.settimeout(timeout)
        s.connect(addr)

        head = "%s %s HTTP/1.1\r\n" % (method, path)
        head += "Host: %s:%d\r\n" % (SERVER_HOST, SERVER_PORT)
        head += "Connection: close\r\n"
        for key, value in headers:
            head += "%s: %s\r\n" % (key, value)
        if body:
            head += "Content-Length: %d\r\n" % len(body)
        head += "\r\n"

        s.send(head.encode())

        if body:
            # 分块发送，20KB 的图一次性 send 在部分固件会报错
            step = 2048
            for i in range(0, len(body), step):
                s.send(body[i:i + step])

        data = b""
        while True:
            try:
                chunk = s.recv(1024)
            except Exception:
                break
            if not chunk:
                break
            data += chunk
            if len(data) > 8192:        # 响应头 + 一点正文就够判断了，不读整包
                break

        try:
            s.close()
        except Exception:
            pass

        return data

    except Exception as exc:
        log("HTTP 失败 %s %s -> %s" % (method, path, exc))
        return b""


def build_multipart(fields, image_bytes=None, filename="shot.jpg", mime="image/jpeg"):
    """
    手工拼 multipart/form-data，和后端 request.form / request.files 对得上。
    fields 是 dict（普通表单字段），image_bytes 是图片字节（可为 None，表示不带图）。
    """
    boundary = "----OpenMVBoundary8f3c2a91"

    out = b""
    for key in fields:
        out += ("--%s\r\n" % boundary).encode()
        out += ('Content-Disposition: form-data; name="%s"\r\n\r\n' % key).encode()
        out += ("%s\r\n" % fields[key]).encode()

    if image_bytes:
        out += ("--%s\r\n" % boundary).encode()
        out += ('Content-Disposition: form-data; name="image"; filename="%s"\r\n' % filename).encode()
        out += ("Content-Type: %s\r\n\r\n" % mime).encode()
        out += image_bytes
        out += b"\r\n"

    out += ("--%s--\r\n" % boundary).encode()
    return out, boundary


# ==============================================================================
# 八、联网
# ==============================================================================
def init_network():
    """按 NET_MODE 初始化联网，返回是否可用。"""
    global _uart

    if NET_MODE == "none":
        log("NET_MODE=none，只识别不上报（用来看识别效果）")
        _state["network_ready"] = False
        return False

    if NET_MODE == "esp32":
        from machine import UART
        _uart = UART(ESP32_UART_ID, ESP32_UART_BAUD)
        log("NET_MODE=esp32，识别结果通过 UART%d 发给 ESP32" % ESP32_UART_ID)
        _state["network_ready"] = True
        return True

    # 默认走官方 WiFi 扩展板
    import network
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        log("正在连接 WiFi：%s" % WIFI_SSID)
        wlan.connect(WIFI_SSID, WIFI_PASSWORD)
        deadline = ticks_now()
        while not wlan.isconnected() and elapsed(deadline) < 20000:
            time.sleep_ms(200)

    if wlan.isconnected():
        log("WiFi 已连接，IP=%s" % wlan.ifconfig()[0])
        _state["network_ready"] = True
        return True

    log("WiFi 连接失败，检查 SSID / 密码 / 是不是 2.4G 频段")
    _state["network_ready"] = False
    return False


def ensure_network():
    """每轮用一下，掉线了自动重连，避免板子跑一夜就哑了。"""
    if NET_MODE != "wlan":
        return _state["network_ready"]
    if _state["network_ready"]:
        return True
    return init_network()


# ==============================================================================
# 九、上报与拉参
# ==============================================================================
def report_record(fruit_type, result, confidence, area, image_bytes):
    """POST /api/device/report，返回是否成功。"""
    fields = {
        "fruit_type": fruit_type,
        "result": result,
        "confidence": "%.3f" % confidence,
        "area": str(area),
    }
    body, boundary = build_multipart(fields, image_bytes)
    headers = [
        ("Content-Type", "multipart/form-data; boundary=%s" % boundary),
        ("X-Device-Token", DEVICE_TOKEN),
    ]

    resp = http_request("POST", "/api/device/report", headers, body)
    status = http_status_line(resp)
    payload = json_body(resp)

    if " 201 " in status or payload.get("code") == 0:
        _state["ok_count"] += 1
        log("上报成功 #%d %s %s area=%d" % (_state["ok_count"], fruit_type, result, area))
        return True

    _state["fail_count"] += 1
    log("上报失败（%s）%s" % (status, payload.get("msg", "")))
    return False


def upload_frame(image_bytes):
    """POST /api/device/frame，充当网页 MJPEG 的实时画面源。"""
    if not image_bytes:
        return False

    body, boundary = build_multipart({}, image_bytes, filename="frame.jpg")
    headers = [
        ("Content-Type", "multipart/form-data; boundary=%s" % boundary),
        ("X-Device-Token", DEVICE_TOKEN),
    ]

    resp = http_request("POST", "/api/device/frame", headers, body)
    return " 200 " in http_status_line(resp)


def pull_settings():
    """GET /api/setting/device，服务端只认 min_area 落地，HSL 打日志供对照。"""
    headers = [("X-Device-Token", DEVICE_TOKEN)]
    resp = http_request("GET", "/api/setting/device", headers, None)

    if " 200 " not in http_status_line(resp):
        log("拉取参数失败：%s" % http_status_line(resp))
        return

    payload = json_body(resp)
    data = payload.get("data") or {}
    if not isinstance(data, dict):
        return

    min_area = data.get("min_area")
    if isinstance(min_area, int) and min_area > 0:
        _state["server_min_area"] = min_area

    _state["server_hsl"] = {
        "h": (data.get("h_min"), data.get("h_max")),
        "s": (data.get("s_min"), data.get("s_max")),
        "v": (data.get("v_min"), data.get("v_max")),
    }

    log("参数已同步 min_area=%d HSL=%s（HSL 仅参考，识别仍用 LAB 阈值）"
        % (_state["server_min_area"], _state["server_hsl"]))


def push_to_esp32(fruit_type, result, confidence, area):
    """esp32 模式下把结果用一行 JSON 交给 ESP32，由它去联网上报。"""
    if _uart is None:
        return
    line = json.dumps({
        "fruit_type": fruit_type,
        "result": result,
        "confidence": round(confidence, 3),
        "area": area,
        "token": DEVICE_TOKEN,
    })
    try:
        _uart.write(line + "\n")
        log("已发给 ESP32：%s" % line)
    except Exception as exc:
        log("串口发送失败：%s" % exc)


# ==============================================================================
# 十、识别与判定
# ==============================================================================
def init_camera():
    """QVGA RGB565，关掉自动增益/白平衡，否则颜色会飘、阈值白调。"""
    sensor.reset()
    sensor.set_pixformat(sensor.RGB565)
    sensor.set_framesize(sensor.QVGA)
    sensor.set_auto_gain(False)
    sensor.set_auto_whitebal(False)
    sensor.skip_frames(time=2000)
    log("摄像头就绪 QVGA RGB565")


def find_best_blob(img):
    """在所有品种的阈值里找面积最大的色块，返回 (品种名, blob)，没有则 (None, None)。"""
    threshold_px = _state["server_min_area"] or MIN_AREA
    best_fruit = None
    best_blob = None

    for fruit in FRUITS:
        blobs = img.find_blobs(
            [fruit["threshold"]],
            pixels_threshold=threshold_px,
            area_threshold=threshold_px,
            merge=True,
        )
        for blob in blobs:
            if blob.pixels() <= 0:
                continue
            if best_blob is None or blob.pixels() > best_blob.pixels():
                best_blob = blob
                best_fruit = fruit["name"]

    return best_fruit, best_blob


def judge(blob):
    """
    判定合格与否：
      面积落在 [GOOD_AREA_MIN, GOOD_AREA_MAX] 之间，且填充率 >= FILL_RATIO_MIN -> good
    置信度这个项目里没有训练模型，用填充率线性映射出一个 0~1 的可信度，写进记录里便于统计。
    """
    area = blob.pixels()
    box = blob.w() * blob.h()
    fill = (area / box) if box else 0.0

    if GOOD_AREA_MIN <= area <= GOOD_AREA_MAX and fill >= FILL_RATIO_MIN:
        # 填充率 0.45 -> 0.60；0.95 -> 1.00
        confidence = 0.60 + (fill - FILL_RATIO_MIN) * 0.8
        return "good", min(1.0, max(0.60, confidence))

    # 不合格的置信度也给出来，但压在 0.6 以下，视觉上区分开
    confidence = 0.40 + fill * 0.20
    return "bad", min(0.60, max(0.40, confidence))


# ==============================================================================
# 十一、主循环
# ==============================================================================
def main():
    init_camera()
    init_network()
    pull_settings()
    _state["last_pull_ms"] = ticks_now()

    log("开始运行，Ctrl-C 可停止")

    while True:
        img = sensor.snapshot()
        now = ticks_now()

        # ---- 1. 定时拉参数（网页改阈值后 10 秒内生效）----
        if elapsed(_state["last_pull_ms"]) > SETTING_PULL_MS:
            _state["last_pull_ms"] = now
            ensure_network()
            pull_settings()

        # ---- 2. 找果实并画标记 ----
        fruit, blob = find_best_blob(img)

        need_report = False
        result = ""
        confidence = 0.0
        area = 0

        if blob is not None:
            result, confidence = judge(blob)
            area = blob.pixels()

            color = (0, 255, 0) if result == "good" else (255, 0, 0)
            img.draw_rectangle(blob.rect(), color=color, thickness=2)
            img.draw_cross(blob.cx(), blob.cy(), color=(255, 255, 0), size=10)
            img.draw_string(
                max(0, blob.x()), max(0, blob.y() - 14),
                "%s %s %d" % (fruit, result, area),
                color=(255, 255, 0), scale=1,
            )

            # 冷却时间内不重复上报，否则同一颗果会连着报很多条
            if elapsed(_state["last_report_ms"]) > REPORT_COOLDOWN_MS:
                need_report = True

        # ---- 3. 需要发数据时才编码一次 JPEG（帧上传和上报复用同一张）----
        need_frame = elapsed(_state["last_frame_ms"]) > FRAME_INTERVAL_MS
        jpeg = capture_jpeg(img) if (need_report or need_frame) else None

        if need_report:
            _state["last_report_ms"] = now
            if NET_MODE == "esp32":
                push_to_esp32(fruit, result, confidence, area)
            elif NET_MODE == "wlan":
                ensure_network()
                report_record(fruit, result, confidence, area, jpeg)

        if need_frame and jpeg:
            _state["last_frame_ms"] = now
            if NET_MODE == "wlan":
                upload_frame(jpeg)

        # ---- 4. 让出 CPU，别把板子烤热 ----
        time.sleep_ms(LOOP_IDLE_MS)


# ==============================================================================
# 十二、入口
# ==============================================================================
if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("已手动停止")
        log("本次统计：成功 %d 条 / 失败 %d 条" % (_state["ok_count"], _state["fail_count"]))
    except Exception as exc:
        log("异常退出：%s" % exc)
        raise
