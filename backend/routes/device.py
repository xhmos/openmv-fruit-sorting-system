# -*- coding: utf-8 -*-
"""设备接口：OpenMV 上报识别结果、上传实时帧、MJPEG 取流，以及后端直连摄像头。"""

import os
import time

from flask import Blueprint, Response, current_app, jsonify, request

from config import Config
from extensions import db, socketio
from models import SavedDevice, SortRecord
from services.camera_service import camera_service
from utils.security import (
    admin_required,
    decode_token,
    device_required,
    login_required,
    sanitize_text,
    save_upload_image,
    write_operation_log,
)

device_bp = Blueprint("device", __name__)


def _as_bool(value, default=False):
    """JSON 里可能是 true / False / "true" / 1，统一成布尔，避免 "false" 被当成真。"""
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")

RESULT_WHITELIST = {"good", "bad"}
LIVE_DIR = os.path.join(Config.UPLOAD_FOLDER, "live")
LIVE_FILE = os.path.join(LIVE_DIR, "latest.jpg")
VIDEO_DIR = os.path.join(Config.UPLOAD_FOLDER, "videos")
VIDEO_EXTS = (".mp4", ".avi", ".mov")


@device_bp.post("/report")
@device_required
def report():
    """OpenMV 识别完成后调用：表单字段 + 一张标记图。"""
    fruit_type = sanitize_text(request.form.get("fruit_type"), 30)
    result = (request.form.get("result") or "").strip().lower()

    if not fruit_type:
        return jsonify(code=400, msg="fruit_type 不能为空"), 400
    if result not in RESULT_WHITELIST:
        return jsonify(code=400, msg="result 只能是 good / bad"), 400

    try:
        confidence = float(request.form.get("confidence", 0))
        area = int(float(request.form.get("area", 0)))
    except (TypeError, ValueError):
        return jsonify(code=400, msg="confidence / area 必须是数字"), 400

    # 收敛到合法区间，脏数据不进库
    confidence = max(0.0, min(1.0, confidence))
    area = max(0, area)

    img_path = ""
    image = request.files.get("image")
    if image is not None and image.filename:
        ok, path_or_msg = save_upload_image(image, sub_dir="records")
        if not ok:
            return jsonify(code=400, msg=path_or_msg), 400
        img_path = path_or_msg

    record = SortRecord(
        fruit_type=fruit_type,
        result=result,
        confidence=confidence,
        area=area,
        img_path=img_path,
    )
    db.session.add(record)
    db.session.commit()

    payload = record.to_dict()
    payload["img_url"] = f"/uploads/{img_path}" if img_path else ""

    # 推给所有在线看板，前端不用刷新
    socketio.emit("new_record", payload)

    return jsonify(code=0, msg="上报成功", data=payload), 201


@device_bp.post("/frame")
@device_required
def upload_frame():
    """OpenMV 持续上传当前画面，覆盖成 latest.jpg，供 MJPEG 取流。"""
    image = request.files.get("image")
    if image is None or not image.filename:
        return jsonify(code=400, msg="未接收到图片"), 400

    ok, path_or_msg = save_upload_image(image, sub_dir="live")
    if not ok:
        return jsonify(code=400, msg=path_or_msg), 400

    os.makedirs(LIVE_DIR, exist_ok=True)
    src = os.path.join(Config.UPLOAD_FOLDER, path_or_msg)
    os.replace(src, LIVE_FILE)  # 原子替换，读端不会读到半个文件

    socketio.emit("live_frame", {"ts": int(time.time() * 1000)})
    return jsonify(code=0, msg="ok")


@device_bp.get("/stream")
def stream():
    """
    MJPEG 实时流。浏览器 <img> 无法带 Authorization 头，
    所以这里用 ?token=<JWT> 校验身份。
    """
    token = request.args.get("token", "")
    if not token:
        return jsonify(code=401, msg="缺少 token"), 401
    try:
        decode_token(token)
    except Exception:
        return jsonify(code=401, msg="token 无效或已过期"), 401

    def gen():
        while True:
            if os.path.exists(LIVE_FILE):
                try:
                    with open(LIVE_FILE, "rb") as f:
                        data = f.read()
                    yield (
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n"
                        b"Content-Length: " + str(len(data)).encode() + b"\r\n\r\n"
                        + data
                        + b"\r\n"
                    )
                except OSError:
                    pass
            time.sleep(0.15)  # 约 6~7 fps，够看画面又不烧 CPU

    return Response(
        gen(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@device_bp.get("/latest")
@login_required
def latest():
    """最新一条分拣记录，页面打开时先渲染一次。"""
    record = db.session.query(SortRecord).order_by(SortRecord.id.desc()).first()
    if record is None:
        return jsonify(code=0, msg="ok", data=None)
    data = record.to_dict()
    data["img_url"] = f"/uploads/{record.img_path}" if record.img_path else ""
    return jsonify(code=0, msg="ok", data=data)


# ======================= 后端直连摄像头 =======================

@device_bp.get("/live")
def live():
    """
    摄像头实时流：直接读内存里那张 JPEG，不落盘。

    与 /stream 的区别：
        /stream —— 读设备端（OpenMV 板 / pc_camera_device.py）上传的 latest.jpg
        /live   —— 读后端自己抓的帧，全程只在内存里，不会写任何文件
    """
    token = request.args.get("token", "")
    if not token:
        return jsonify(code=401, msg="缺少 token"), 401
    try:
        decode_token(token)
    except Exception:
        return jsonify(code=401, msg="token 无效或已过期"), 401

    def gen():
        last_ts = 0.0
        while True:
            data, ts = camera_service.latest_jpeg()
            if data and ts != last_ts:
                last_ts = ts
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    b"Content-Length: " + str(len(data)).encode() + b"\r\n\r\n"
                    + data
                    + b"\r\n"
                )
            else:
                time.sleep(0.05)  # 还没新帧，别空转烧 CPU

    return Response(
        gen(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@device_bp.get("/camera/status")
@login_required
def camera_status():
    """采集服务状态：有没有在跑、三个开关、命中/截图/录像计数。"""
    return jsonify(code=0, msg="ok", data=camera_service.status())


@device_bp.post("/camera/start")
@admin_required
def camera_start():
    """启动采集。没指定 source 时自动挑「我的设备」里第一个摄像头。"""
    body = request.get_json(silent=True) or {}
    source = str(body.get("source") or "").strip()

    if not source:
        dev = (
            SavedDevice.query.filter_by(dev_type="camera")
            .order_by(SavedDevice.id.asc())
            .first()
        )
        source = dev.target if dev else "0"

    try:
        fps = int(body.get("fps") or 8)
        min_area = int(body.get("min_area") or 300)
        cooldown = float(body.get("cooldown") or 3.0)
        min_confidence = float(body.get("min_confidence") or 0.65)
    except (TypeError, ValueError):
        return jsonify(code=400, msg="fps / min_area / cooldown / min_confidence 必须是数字"), 400

    ok, msg = camera_service.start(
        current_app._get_current_object(),
        source=source,
        fps=fps,
        detect=_as_bool(body.get("detect"), True),
        snapshot=_as_bool(body.get("snapshot"), True),
        record=_as_bool(body.get("record"), False),
        min_area=min_area,
        cooldown=cooldown,
        min_confidence=min_confidence,
    )

    write_operation_log("启动摄像头采集", target=source, detail="fps=%d" % fps)
    db.session.commit()

    return jsonify(code=0 if ok else 500, msg=msg, data=camera_service.status())


@device_bp.post("/camera/stop")
@admin_required
def camera_stop():
    """停止采集，释放摄像头。"""
    ok, msg = camera_service.stop()
    write_operation_log("停止摄像头采集", target="camera", detail="")
    db.session.commit()
    return jsonify(code=0, msg=msg, data=camera_service.status())


@device_bp.patch("/camera/config")
@admin_required
def camera_config():
    """
    运行中切换开关，不用重启摄像头。
    detect=识别 / snapshot=命中存图并写记录 / record=命中另存短视频，三者互相独立。
    """
    body = request.get_json(silent=True) or {}
    kwargs = {}

    if "detect" in body:
        kwargs["detect"] = _as_bool(body.get("detect"))
    if "snapshot" in body:
        kwargs["snapshot"] = _as_bool(body.get("snapshot"))
    if "record" in body:
        kwargs["record"] = _as_bool(body.get("record"))
    if "min_area" in body:
        try:
            kwargs["min_area"] = int(body.get("min_area"))
        except (TypeError, ValueError):
            return jsonify(code=400, msg="min_area 必须是数字"), 400
    if "cooldown" in body:
        try:
            kwargs["cooldown"] = float(body.get("cooldown"))
        except (TypeError, ValueError):
            return jsonify(code=400, msg="cooldown 必须是数字"), 400
    if "min_confidence" in body:
        try:
            kwargs["min_confidence"] = float(body.get("min_confidence"))
        except (TypeError, ValueError):
            return jsonify(code=400, msg="min_confidence 必须是数字"), 400

    return jsonify(code=0, msg="ok", data=camera_service.update_switches(**kwargs))


# ---------------------------------------------------------------- 录像文件
def _size_text(size):
    if size >= 1024 * 1024:
        return f"{size / 1024 / 1024:.1f} MB"
    if size >= 1024:
        return f"{size / 1024:.0f} KB"
    return f"{size} B"


@device_bp.get("/videos")
@login_required
def list_videos():
    """列出 uploads/videos 下的录像文件，按时间倒序。"""
    items = []
    if os.path.isdir(VIDEO_DIR):
        for name in os.listdir(VIDEO_DIR):
            if not name.lower().endswith(VIDEO_EXTS):
                continue
            abs_path = os.path.join(VIDEO_DIR, name)
            if not os.path.isfile(abs_path):
                continue
            try:
                st = os.stat(abs_path)
            except OSError:
                continue
            items.append({
                "name": name,
                "size": st.st_size,
                "size_text": _size_text(st.st_size),
                "mtime": int(st.st_mtime),
                "create_time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime)),
                # 前端直接拼 API_BASE 用，路径固定在这一个位置
                "url": f"/uploads/videos/{name}",
            })

    items.sort(key=lambda x: x["mtime"], reverse=True)
    return jsonify(code=0, msg="ok", data={"items": items, "total": len(items)})


@device_bp.delete("/videos/<name>")
@admin_required
def delete_video(name):
    """
    删除一段录像。
    只接受纯文件名（不含目录、不含 ..），并用 realpath 复核落点，
    防止有人构造 ../../ 去删别处的文件。
    """
    if name != os.path.basename(name) or ".." in name:
        return jsonify(code=400, msg="文件名不合法"), 400
    if not name.lower().endswith(VIDEO_EXTS):
        return jsonify(code=400, msg="只允许删除视频文件"), 400

    abs_path = os.path.realpath(os.path.join(VIDEO_DIR, name))
    video_root = os.path.realpath(VIDEO_DIR)
    if not abs_path.startswith(video_root + os.sep):
        return jsonify(code=400, msg="文件名不合法"), 400
    if not os.path.isfile(abs_path):
        return jsonify(code=404, msg="文件不存在"), 404

    try:
        os.remove(abs_path)
    except OSError as e:
        return jsonify(code=500, msg=f"删除失败：{e}"), 500

    write_operation_log("删除录像", target=name, detail="uploads/videos")
    db.session.commit()
    return jsonify(code=0, msg="已删除")
