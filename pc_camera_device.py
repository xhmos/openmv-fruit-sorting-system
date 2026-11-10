# -*- coding: utf-8 -*-
"""
用「电脑 USB 摄像头」替代 OpenMV 当设备端（PC 版采集程序）

适用场景：
    手上的机械臂 / 摄像头是标准 USB 摄像头（Windows 设备管理器里能看到 UVC WebCam），
    没有 OpenMV 板子，但想跑真实的识别 + 上报 + 看板实时画面。

它做的事和 openmv_script/main.py 完全一样，只是把「板端」换成了「电脑端」：
    抓帧 → HSV 找色块 → 判定合格/不合格 → 画标记框 → POST 上报 → 推帧给看板 MJPEG

依赖（只需一次）：
    .\\backend\\venv\\Scripts\\python.exe -m pip install opencv-python

用法：
    # 先看能不能拿到画面（不联网、不上报）
    .\\backend\\venv\\Scripts\\python.exe pc_camera_device.py --index 0 --frames 10 --dry-run

    # 正式跑：每帧推给看板，每 5 帧尝试上报一次
    .\\backend\\venv\\Scripts\\python.exe pc_camera_device.py --index 0 --report-every 5 --frames 999

    # 多个摄像头时换 index：0 通常是内置，1 是外接
    .\\backend\\venv\\Scripts\\python.exe pc_camera_device.py --index 1

参数说明：
    --index         摄像头序号，默认 0
    --frames        抓多少帧后退出，0 = 一直跑
    --interval      帧间隔秒，默认 0.5（不要低于 0.3，会撞 200 次/分钟限流）
    --report-every  每多少帧尝试上报一次，默认 5
    --min-area      最小色块面积（像素），默认 300，与参数页默认一致
    --dry-run       不联网，只在本地检测并打印结果
    --force-fruit   检测不到色块时也按指定品种上报一次（仅用于验证链路，如 --force-fruit apple）
"""

import argparse
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid

import cv2
import numpy as np

# HSV 阈值预设：每个品种可有多段（红色在 H 上跨 0，所以要两段）
# 注意：这是「演示用」的经验值，实际光照下要自己调，跟板子上的 LAB 阈值是两套体系。
FRUITS = {
    "apple": [((0, 80, 60), (10, 255, 255)), ((160, 80, 60), (179, 255, 255))],
    "lemon": [((20, 100, 80), (35, 255, 255))],
    "mango": [((15, 90, 80), (30, 255, 255))],
    "peach": [((10, 80, 60), (20, 255, 255))],
    "pear": [((35, 40, 80), (85, 255, 255))],
}

FRUIT_LABEL = {
    "apple": "苹果",
    "lemon": "柠檬",
    "mango": "芒果",
    "peach": "桃子",
    "pear": "梨",
}


def encode_multipart(fields, files):
    """用标准库手拼 multipart/form-data，避免额外装 requests。"""
    boundary = "----pcCameraBoundary" + uuid.uuid4().hex
    body = io.BytesIO()
    for key, value in fields.items():
        body.write(("--%s\r\n" % boundary).encode())
        body.write(('Content-Disposition: form-data; name="%s"\r\n\r\n' % key).encode())
        body.write(str(value).encode() + b"\r\n")
    for key, (filename, content, ctype) in files.items():
        body.write(("--%s\r\n" % boundary).encode())
        body.write(
            ('Content-Disposition: form-data; name="%s"; filename="%s"\r\n' % (key, filename)).encode()
        )
        body.write(("Content-Type: %s\r\n\r\n" % ctype).encode())
        body.write(content + b"\r\n")
    body.write(("--%s--\r\n" % boundary).encode())
    return body.getvalue(), "multipart/form-data; boundary=%s" % boundary


def post(server, path, fields, files, device_token, timeout=8):
    data, ctype = encode_multipart(fields, files)
    req = urllib.request.Request(server.rstrip("/") + path, data=data, method="POST")
    req.add_header("Content-Type", ctype)
    req.add_header("X-Device-Token", device_token)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8", "ignore"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "ignore")
        try:
            return e.code, json.loads(body)
        except Exception:
            return e.code, {"msg": body[:120]}
    except Exception as e:
        return 0, {"msg": str(e)}


def detect(frame, min_area):
    """在画面里找色块，返回面积最大的那个（品种 + 面积 + 置信度 + 外框）。"""
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
            if best is not None and area <= best["area"]:
                continue
            x, y, w, h = cv2.boundingRect(c)
            # 置信度用「填充率」近似：圆润的果实外接框填充率高，畸形/散落的低
            fill = area / float(w * h) if w * h else 0.0
            best = {
                "fruit": fruit,
                "area": int(area),
                "bbox": (x, y, w, h),
                "confidence": round(min(0.99, max(0.05, fill)), 3),
            }
    return best


def annotate(frame, det):
    """画标记框 + 文字，这张图会作为记录图片上传（看板上点开就是它）。"""
    if not det:
        cv2.putText(frame, "no fruit detected", (10, 24),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
        return frame

    x, y, w, h = det["bbox"]
    ok = det["confidence"] >= 0.6
    color = (0, 200, 0) if ok else (0, 165, 255)
    cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
    label = "%s %.2f A%d" % (det["fruit"], det["confidence"], det["area"])
    cv2.putText(frame, label, (x, max(18, y - 8)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
    return frame


def to_jpeg(frame, quality=80):
    ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:
        raise RuntimeError("JPEG 编码失败")
    return buf.tobytes()


def main():
    ap = argparse.ArgumentParser(description="用电脑摄像头替代 OpenMV 做采集与上报")
    ap.add_argument("--index", type=str, default="0",
                    help="摄像头序号（0=内置、1=外接）或 MJPEG 流地址（如 http://192.168.1.5:8080/video）")
    ap.add_argument("--server", default="http://127.0.0.1:5000")
    ap.add_argument("--device-token", default="openmv-device-2026")
    ap.add_argument("--frames", type=int, default=0, help="抓多少帧后退出，0=一直跑")
    ap.add_argument("--interval", type=float, default=0.5)
    ap.add_argument("--report-every", type=int, default=5)
    ap.add_argument("--min-area", type=int, default=300)
    ap.add_argument("--dry-run", action="store_true", help="不联网，只本地检测")
    ap.add_argument("--force-fruit", default="", help="检测不到也按该品种上报一次（验证链路用）")
    ap.add_argument("--save-debug", default="", help="把最后一张标注图存到这个路径")
    args = ap.parse_args()

    # --index 既可以是本地摄像头序号，也可以是手机/IP 摄像头的 MJPEG 地址
    if args.index.isdigit():
        cap = cv2.VideoCapture(int(args.index), cv2.CAP_DSHOW)
        source_desc = "摄像头 index=%s" % args.index
    else:
        cap = cv2.VideoCapture(args.index)
        source_desc = "网络流 %s" % args.index

    if not cap.isOpened():
        print("[错误] 打不开 %s。本地摄像头换个 --index（0/1/2）；网络流请确认地址与手机在同一 WiFi。" % source_desc)
        return 1

    ok, probe = cap.read()
    if not ok:
        print("[错误] %s 能打开但拿不到画面，可能被占用、地址失效或驱动异常。" % source_desc)
        cap.release()
        return 1

    print("已连接：%s，分辨率 %dx%d" % (source_desc, probe.shape[1], probe.shape[0]))
    print("目标：%s，帧间隔 %.2fs，每 %d 帧尝试上报一次，min_area=%d" % (
        args.server, args.interval, args.report_every, args.min_area))
    print("-" * 56)

    frame_no = 0
    report_ok = 0
    report_fail = 0
    forced_done = False
    last_annotated = None

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("[警告] 读帧失败，稍后重试")
                time.sleep(args.interval)
                continue

            frame_no += 1
            det = detect(frame, args.min_area)
            annotated = annotate(frame.copy(), det)
            last_annotated = annotated

            result_text = "无"
            if det:
                result_text = "%s / area=%d / conf=%.2f" % (
                    det["fruit"], det["area"], det["confidence"])

            # 1) 推帧给看板（MJPEG 靠这个刷新，不联网就跳过）
            if not args.dry_run:
                status, body = post(args.server, "/api/device/frame",
                                    {}, {"image": ("frame.jpg", to_jpeg(annotated), "image/jpeg")},
                                    args.device_token)
                if status != 200:
                    print("[帧] 推送失败 %s %s" % (status, body.get("msg")))

            # 2) 每隔 N 帧尝试上报一条记录（只在检测到色块时上报，空画面不写库）
            should_report = (frame_no % args.report_every == 0) and (det is not None or args.force_fruit)
            if should_report and not args.dry_run:
                fruit = det["fruit"] if det else args.force_fruit
                if det:
                    result = "good" if det["confidence"] >= 0.6 else "bad"
                    conf = det["confidence"]
                    area = det["area"]
                else:
                    result, conf, area = "good", 0.5, args.min_area
                status, body = post(
                    args.server, "/api/device/report",
                    {"fruit_type": fruit, "result": result,
                     "confidence": conf, "area": area},
                    {"image": ("shot.jpg", to_jpeg(annotated), "image/jpeg")},
                    args.device_token,
                )
                if status == 201:
                    report_ok += 1
                    print("[上报 %d] %s / %s / %.3f / area=%d -> 201"
                          % (report_ok, fruit, result, conf, area))
                else:
                    report_fail += 1
                    print("[上报失败] %s %s" % (status, body.get("msg")))
                if args.force_fruit:
                    forced_done = True

            # 3) 控制台进度
            if frame_no <= 3 or frame_no % 10 == 0:
                print("[帧 %d] 检测：%s" % (frame_no, result_text))

            if args.force_fruit and forced_done:
                print("强制上报已完成，退出")
                break
            if args.frames and frame_no >= args.frames:
                break

            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n已手动停止")
    finally:
        cap.release()
        if args.save_debug and last_annotated is not None:
            cv2.imwrite(args.save_debug, last_annotated)
            print("标注图已保存：%s" % args.save_debug)

    print("-" * 56)
    print("帧：%d；上报：成功 %d / 失败 %d" % (frame_no, report_ok, report_fail))
    if not args.dry_run:
        print("打开 http://localhost:5173 的看板，能看到实时画面与统计刷新")
    return 0


if __name__ == "__main__":
    sys.exit(main())
