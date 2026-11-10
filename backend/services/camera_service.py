# -*- coding: utf-8 -*-
"""
摄像头采集服务（后端直连摄像头）

为什么要有它：
    原来前端看到的「实时画面」是设备端（OpenMV 板或 pc_camera_device.py）
    先抓帧、写成 latest.jpg、再由 MJPEG 接口读文件喂给浏览器——
    也就是说每一帧都在写盘，而且想看看画面就必须另开一个程序。
    现在改成由后端自己开摄像头：

        摄像头 → 后台线程抓帧 → 内存里的一张 JPEG（不落盘）
                              → /api/device/live 直接把内存那张推给浏览器

    只有「检测到果实」时才会真的写文件（截图存档），
    录像则是一个完全独立的开关，与截图互不影响。

三个开关是分开的（这就是「把是否录像单独取出来」的落地）：
    detect   —— 跑不跑识别。关掉就只是纯看画面，不产生任何记录。
    snapshot —— 命中时要不要存一张证据图并写一条分拣记录。
    record   —— 命中时要不要另存一段短视频（命中前缓冲 + 之后 2 秒）。

资源上的注意：
    摄像头同一时间只能被一个程序打开。服务启动后 pc_camera_device.py
    就打不开了，前端会明确提示「采集服务正在占用摄像头」。
"""

import collections
import os
import threading
import time
from datetime import datetime

import cv2
import numpy as np

from config import Config
from extensions import db, socketio
from models import SortRecord

# HSV 预设与 pc_camera_device.py 保持一致（演示用经验值，实拍要按光照调）
FRUITS = {
    "apple": [((0, 80, 60), (10, 255, 255)), ((160, 80, 60), (179, 255, 255))],
    "lemon": [((20, 100, 80), (35, 255, 255))],
    "mango": [((15, 90, 80), (30, 255, 255))],
    "peach": [((10, 80, 60), (20, 255, 255))],
    "pear": [((35, 40, 80), (85, 255, 255))],
}

VIDEO_DIR_NAME = "videos"

_VIDEO_SUPPORT = {"checked": False, "ok": False}


def detect_fruit(frame, min_area):
    """在画面里找面积最大的色块，返回 (品种, 面积, 置信度, 外框) 或 None。"""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    best = None

    for fruit, segments in FRUITS.items():
        mask = None
        for lo, hi in segments:
            m = cv2.inRange(hsv, np.array(lo, dtype=np.uint8), np.array(hi, dtype=np.uint8))
            mask = m if mask is None else cv2.bitwise_or(mask, m)

        # 开运算去噪点、闭运算补空洞——和 OpenMV 里 morphology 的思路一致
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in contours:
            area = cv2.contourArea(c)
            if area < min_area:
                continue
            if best is not None and area <= best[1]:
                continue
            x, y, w, h = cv2.boundingRect(c)
            # 置信度用「外接框填充率」近似：圆润的果实填充率高，散落的低
            fill = area / float(w * h) if w * h else 0.0
            best = (fruit, int(area), round(min(0.99, max(0.05, fill)), 3), (x, y, w, h))
    return best


def annotate(frame, det):
    """画标记框，存下来的证据图就是这张。返回新图，不改原帧。"""
    out = frame.copy()
    if not det:
        cv2.putText(out, "no fruit", (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
        return out

    fruit, area, conf, (x, y, w, h) = det
    color = (0, 200, 0) if conf >= 0.6 else (0, 165, 255)
    cv2.rectangle(out, (x, y), (x + w, y + h), color, 2)
    cv2.putText(out, "%s %.2f A%d" % (fruit, conf, area), (x, max(18, y - 8)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
    return out


def video_supported():
    """试探当前 opencv 构建能不能写 mp4，不能就让前端把录像开关灰掉。一次测完就缓存。"""
    if _VIDEO_SUPPORT["checked"]:
        return _VIDEO_SUPPORT["ok"]
    _VIDEO_SUPPORT["checked"] = True
    tmp = os.path.join(Config.UPLOAD_FOLDER, "_video_probe.mp4")
    try:
        os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
        w = cv2.VideoWriter(tmp, cv2.VideoWriter_fourcc(*"mp4v"), 8, (320, 240))
        _VIDEO_SUPPORT["ok"] = bool(w.isOpened())
        w.release()
    except Exception:
        _VIDEO_SUPPORT["ok"] = False
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
    return _VIDEO_SUPPORT["ok"]


def open_capture(source):
    """
    打开一路视频源，返回 (cap, 实际使用的描述) 或 (None, 错误说明)。

    为什么要这一层：
        OpenCV 的 VideoCapture 只认「摄像头编号」或「文件/流地址」，
        不认 Windows 的设备名。而「我的设备」里摄像头存的恰恰是设备名
        （比如 USB2.0 HD UVC WebCam），直接丢给 VideoCapture 一定打不开。
    """
    src = str(source or "").strip()

    # 1) 纯数字：按编号打开
    if src.isdigit():
        cap = cv2.VideoCapture(int(src), cv2.CAP_DSHOW)
        if cap.isOpened():
            return cap, "摄像头 #%s" % src
        cap.release()
        return None, "打不开摄像头 #%s：可能被其他程序占用或没有接好" % src

    # 2) 网络流地址：原样打开（手机 MJPEG 之类）
    if src.startswith("http://") or src.startswith("https://"):
        cap = cv2.VideoCapture(src)
        if cap.isOpened():
            return cap, src
        cap.release()
        return None, "打不开网络流 %s：检查地址与手机是否在同一 WiFi" % src

    # 3) Windows 设备名：OpenCV 认不了，按 0~4 依次试，取第一个能出帧的
    for idx in range(5):
        cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
        if not cap.isOpened():
            cap.release()
            continue
        ok, frame = cap.read()
        if ok and frame is not None:
            return cap, "摄像头 #%d（按设备名「%s」自动匹配）" % (idx, src)
        cap.release()

    return None, (
        "按设备名「%s」没找到可用摄像头：确认它没被别的程序占用，"
        "或到「设备连接」页把摄像头改成编号 0/1" % src
    )


class CameraService:
    """单例采集服务：全局只有一个线程，随进程生命周期。"""

    def __init__(self):
        self._lock = threading.RLock()
        self._thread = None
        self._stop = threading.Event()
        self._app = None
        self._latest_jpeg = b""
        self._latest_ts = 0.0
        self._status = {
            "running": False,
            "source": "",
            "error": "",
            "fps": 8,
            "frames": 0,
            "width": 0,
            "height": 0,
            "started_at": "",
            "detect": True,
            "snapshot": True,
            "record": False,
            "hits": 0,
            "snapshots": 0,
            "videos": 0,
            "last_hit": None,
            "last_snapshot": "",
            "last_video": "",
            "min_area": 300,
            "cooldown": 3.0,
            "min_confidence": 0.65,
            "video_supported": False,
        }

    # ---------------- 对外接口 ----------------

    def status(self):
        with self._lock:
            data = dict(self._status)
            data["has_frame"] = bool(self._latest_jpeg)
            data["frame_at"] = round(self._latest_ts, 3)
            return data

    def latest_jpeg(self):
        with self._lock:
            return self._latest_jpeg, self._latest_ts

    def start(self, app, source="0", fps=8, detect=True, snapshot=True, record=False,
              min_area=300, cooldown=3.0, min_confidence=0.65, width=640):
        """启动采集。已在运行则先停再起。返回 (成功?, 说明)。"""
        with self._lock:
            if self._status["running"]:
                self._do_stop()

        self._app = app
        self._stop.clear()
        self._latest_jpeg = b""
        self._latest_ts = 0.0

        with self._lock:
            self._status.update({
                "running": False,
                "source": source,
                "error": "",
                "fps": max(1, min(30, int(fps))),
                "frames": 0,
                "width": 0,
                "height": 0,
                "started_at": "",
                "detect": bool(detect),
                "snapshot": bool(snapshot),
                "record": bool(record),
                "hits": 0,
                "snapshots": 0,
                "videos": 0,
                "last_hit": None,
                "last_snapshot": "",
                "last_video": "",
                "min_area": int(min_area),
                "cooldown": float(cooldown),
                "min_confidence": float(min_confidence),
                "video_supported": video_supported(),
            })

        self._thread = threading.Thread(
            target=self._loop, args=(source, width), name="camera-service", daemon=True
        )
        self._thread.start()

        # 等线程把摄像头打开，最多等 2 秒，接口才能当场告诉用户成功还是失败
        deadline = time.time() + 2.0
        while time.time() < deadline:
            with self._lock:
                if self._status["running"] or self._status["error"]:
                    break
            time.sleep(0.1)

        with self._lock:
            if self._status["running"]:
                return True, "采集已启动"
            return False, self._status["error"] or "启动超时：摄像头没有响应"

    def stop(self):
        with self._lock:
            self._do_stop()
        return True, "采集已停止"

    def update_switches(self, detect=None, snapshot=None, record=None, min_area=None,
                        cooldown=None, min_confidence=None):
        """运行中切换开关，不用重启摄像头。"""
        with self._lock:
            if detect is not None:
                self._status["detect"] = bool(detect)
            if snapshot is not None:
                self._status["snapshot"] = bool(snapshot)
            if record is not None:
                self._status["record"] = bool(record)
            if min_area is not None:
                self._status["min_area"] = max(1, int(min_area))
            if cooldown is not None:
                self._status["cooldown"] = max(0.5, float(cooldown))
            if min_confidence is not None:
                self._status["min_confidence"] = max(0.0, min(0.99, float(min_confidence)))
            return dict(self._status)

    # ---------------- 内部实现 ----------------

    def _do_stop(self):
        self._stop.set()
        t = self._thread
        if t is not None and t.is_alive() and t is not threading.current_thread():
            t.join(timeout=3)
        self._thread = None
        with self._lock:
            self._status["running"] = False
            self._latest_jpeg = b""

    def _loop(self, source, width):
        cap, desc = open_capture(source)
        if cap is None:
            with self._lock:
                self._status["error"] = desc
            return

        ok, first = cap.read()
        if not ok or first is None:
            cap.release()
            with self._lock:
                self._status["error"] = "%s 打开了但拿不到画面" % desc
            return

        with self._lock:
            self._status["running"] = True
            self._status["source"] = desc
            self._status["started_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._status["width"] = int(first.shape[1])
            self._status["height"] = int(first.shape[0])

        # 帧缓冲：录像时用来回溯命中前那几秒
        buffer = collections.deque(maxlen=24)
        video_job = None
        last_hit_ts = 0.0
        fail_count = 0

        try:
            while not self._stop.is_set():
                ok, frame = cap.read()
                if not ok or frame is None:
                    fail_count += 1
                    if fail_count > 30:
                        with self._lock:
                            self._status["error"] = "连续读帧失败，摄像头可能被拔掉或断开了"
                        break
                    time.sleep(0.1)
                    continue
                fail_count = 0

                # 统一缩到固定宽度，保证缓冲和录像是同一尺寸
                if width and frame.shape[1] > width:
                    ratio = width / float(frame.shape[1])
                    frame = cv2.resize(frame, (width, int(frame.shape[0] * ratio)))

                with self._lock:
                    fps = self._status["fps"]
                    detect_on = self._status["detect"]
                    snapshot_on = self._status["snapshot"]
                    record_on = self._status["record"]
                    min_area = self._status["min_area"]
                    cooldown = self._status["cooldown"]
                    min_conf = self._status["min_confidence"]

                # 1) 内存里的最新帧——前端 MJPEG 直接读它，不写盘
                ok_jpg, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                if ok_jpg:
                    with self._lock:
                        self._latest_jpeg = buf.tobytes()
                        self._latest_ts = time.time()
                        self._status["frames"] += 1
                        self._status["width"] = int(frame.shape[1])
                        self._status["height"] = int(frame.shape[0])

                # 2) 录像缓冲只在真的要录的时候才占内存
                if record_on:
                    buffer.append(frame)
                elif buffer:
                    buffer.clear()

                # 3) 识别 + 命中处理
                if detect_on:
                    det = detect_fruit(frame, min_area)
                    now = time.time()
                    # 置信度太低的不算命中：室内画面里人脸、木纹、暖色墙面
                    # 很容易被判成 apple/peach，不设门槛就会把库里灌满垃圾记录
                    if det and det[2] >= min_conf and (now - last_hit_ts) >= cooldown:
                        last_hit_ts = now
                        job = self._on_hit(frame, det, snapshot_on, record_on, buffer,
                                           video_job is not None)
                        if job is not None and video_job is None:
                            video_job = job

                # 4) 正在录的那一段，继续把后续帧写进去
                if video_job is not None:
                    video_job["writer"].write(frame)
                    video_job["left"] -= 1
                    if video_job["left"] <= 0:
                        video_job["writer"].release()
                        with self._lock:
                            self._status["videos"] += 1
                            self._status["last_video"] = video_job["rel_path"]
                        video_job = None

                time.sleep(max(0.0, 1.0 / max(1, fps)))
        finally:
            try:
                cap.release()
            except Exception:
                pass
            if video_job is not None:
                try:
                    video_job["writer"].release()
                except Exception:
                    pass
            with self._lock:
                self._status["running"] = False

    def _on_hit(self, frame, det, do_snapshot, do_record, buffer, video_busy=False):
        """
        检测到果实：按开关决定存图 / 写记录 / 录像。
        返回录像任务（交给主循环继续写帧），没录像时返回 None。
        """
        fruit, area, conf = det[0], det[1], det[2]
        with self._lock:
            self._status["hits"] += 1
            self._status["last_hit"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if do_snapshot:
            try:
                _, img_rel = self._save_snapshot(frame, det)
                with self._lock:
                    self._status["snapshots"] += 1
                    self._status["last_snapshot"] = img_rel
                self._write_record(fruit, area, conf, img_rel)
            except Exception as e:
                with self._lock:
                    self._status["error"] = "截图失败：%s" % str(e)[:100]

        # 上一段还没录完就不叠着开，避免两个 VideoWriter 抢同一个文件
        if do_record and not video_busy:
            return self._start_video(frame, det, buffer)
        return None

    def _save_snapshot(self, frame, det):
        """命中才写盘：一张标注过的证据图。"""
        folder = os.path.join(Config.UPLOAD_FOLDER, "records")
        os.makedirs(folder, exist_ok=True)
        name = datetime.now().strftime("%Y%m%d%H%M%S%f")[:18] + "_cam.jpg"
        abs_path = os.path.join(folder, name)
        cv2.imwrite(abs_path, annotate(frame, det), [int(cv2.IMWRITE_JPEG_QUALITY), 90])
        return abs_path, "records/" + name

    def _write_record(self, fruit, area, conf, img_rel):
        """写一条分拣记录并推给看板。后台线程要自己带 app 上下文。"""
        try:
            with self._app.app_context():
                rec = SortRecord(
                    fruit_type=fruit,
                    result="good" if conf >= 0.6 else "bad",
                    confidence=float(conf),
                    area=int(area),
                    img_path=img_rel,
                )
                db.session.add(rec)
                db.session.commit()

                payload = rec.to_dict()
                payload["img_url"] = "/uploads/" + img_rel
                socketio.emit("new_record", payload)
        except Exception as e:
            with self._lock:
                self._status["error"] = "写记录失败：%s" % str(e)[:100]

    def _start_video(self, frame, det, buffer):
        """开始录一段：命中前缓冲的帧 + 之后 2 秒。返回任务字典给主循环续写。"""
        try:
            folder = os.path.join(Config.UPLOAD_FOLDER, VIDEO_DIR_NAME)
            os.makedirs(folder, exist_ok=True)
            name = datetime.now().strftime("%Y%m%d%H%M%S") + "_cam.mp4"
            abs_path = os.path.join(folder, name)

            h, w = frame.shape[0], frame.shape[1]
            with self._lock:
                fps = max(1, int(self._status["fps"]))
            writer = cv2.VideoWriter(abs_path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
            if not writer.isOpened():
                writer.release()
                with self._lock:
                    self._status["error"] = "当前 opencv 写不了 mp4，录像功能不可用"
                    self._status["video_supported"] = False
                return None

            # 先把命中前缓冲的帧补进去，画面才不会从果实正中间才开始
            for f in buffer:
                writer.write(f)

            return {
                "writer": writer,
                "left": fps * 2,  # 命中后再录 2 秒
                "rel_path": "videos/" + name,
            }
        except Exception as e:
            with self._lock:
                self._status["error"] = "录像失败：%s" % str(e)[:100]
            return None


camera_service = CameraService()
