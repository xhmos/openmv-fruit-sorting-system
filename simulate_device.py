# -*- coding: utf-8 -*-
"""
模拟 OpenMV 设备（没有板子时的演示 / 联调工具）

作用：用电脑上的图片冒充板子，按固定节奏把「当前画面」和「分拣结果」发给后端，
      看板上的实时画面、统计卡片、趋势图、实时推送都能跟着动起来。

用法（在项目根目录，用后端 venv 的 python 跑）：
    .\\backend\\venv\\Scripts\\python.exe simulate_device.py
    .\\backend\\venv\\Scripts\\python.exe simulate_device.py --frames 30 --interval 1
    .\\backend\\venv\\Scripts\\python.exe simulate_device.py --frames 0 --reports 5
按 Ctrl+C 随时停止。

参数说明：
    --frames        上传多少帧画面（0 表示只上报记录、不传画面）
    --interval      帧间隔秒（默认 1.0；低于 0.3 会撞后端 200 次/分的限流）
    --report-every  每上传多少帧上报一条分拣记录（0 表示不上报）
    --reports       额外补上报多少条记录（配合 --frames 0 用）
    --img           用作画面的图片路径，默认自动找 latest.jpg
"""

import argparse
import os
import random
import socket
import sys
import time
import urllib.error
import urllib.request

# 固定字段名以匹配后端 /api/device/report 与 /api/device/frame
FRUIT_POOL = ["lemon", "mango", "pear", "grape", "apple"]


def find_demo_image(user_path=""):
    """找一张能当画面的图片：优先用户指定，其次后端已有的 latest.jpg。"""
    candidates = []
    if user_path:
        candidates.append(user_path)
    here = os.path.dirname(os.path.abspath(__file__))
    candidates.append(os.path.join(here, "backend", "uploads", "live", "latest.jpg"))
    candidates.append(os.path.join(here, "backend", "uploads", "records"))
    for c in candidates:
        if os.path.isfile(c):
            return c
    # 兜底：records 目录里随便挑一张
    rec_dir = os.path.join(here, "backend", "uploads", "records")
    if os.path.isdir(rec_dir):
        for name in sorted(os.listdir(rec_dir)):
            if name.lower().endswith((".jpg", ".jpeg", ".png")):
                return os.path.join(rec_dir, name)
    return ""


def build_multipart(fields, file_field, filename, file_bytes, mime="image/jpeg"):
    """手拼 multipart/form-data，只依赖标准库，不需要 requests。"""
    boundary = "----simulate%d" % int(time.time() * 1000)
    parts = []
    for name, value in fields.items():
        parts.append(
            ('--%s\r\nContent-Disposition: form-data; name="%s"\r\n\r\n' % (boundary, name)).encode("utf-8")
            + str(value).encode("utf-8")
            + b"\r\n"
        )
    if file_bytes:
        parts.append(
            (
                '--%s\r\nContent-Disposition: form-data; name="%s"; filename="%s"\r\n'
                "Content-Type: %s\r\n\r\n" % (boundary, file_field, filename, mime)
            ).encode("utf-8")
            + file_bytes
            + b"\r\n"
        )
    parts.append(("--%s--\r\n" % boundary).encode("utf-8"))
    return boundary, b"".join(parts)


class Device(object):
    def __init__(self, base_url, token, timeout=10):
        self.base_url = base_url
        self.token = token
        self.timeout = timeout

    def _post(self, path, fields, file_bytes=None, filename="frame.jpg"):
        boundary, body = build_multipart(fields, "image", filename, file_bytes)
        req = urllib.request.Request(self.base_url + path, data=body, method="POST")
        req.add_header("Content-Type", "multipart/form-data; boundary=" + boundary)
        req.add_header("X-Device-Token", self.token)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.status, resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace")
        except Exception as e:  # 网络不通等
            return 0, str(e)

    def health(self):
        try:
            with urllib.request.urlopen(self.base_url + "/api/health", timeout=self.timeout) as resp:
                return resp.status
        except Exception:
            return 0

    def send_frame(self, file_bytes):
        return self._post("/api/device/frame", {}, file_bytes)

    def send_report(self, fruit, result, confidence, area, file_bytes):
        fields = {
            "fruit_type": fruit,
            "result": result,
            "confidence": "%.3f" % confidence,
            "area": int(area),
        }
        return self._post("/api/device/report", fields, file_bytes, "record.jpg")


def make_record():
    """模拟一次识别结果：约 7 成合格，不合格的面积偏小、置信度偏低。"""
    fruit = random.choice(FRUIT_POOL)
    if random.random() < 0.7:
        return fruit, "good", random.uniform(0.80, 0.98), random.randint(900, 2200)
    return fruit, "bad", random.uniform(0.42, 0.72), random.randint(320, 780)


def main():
    parser = argparse.ArgumentParser(description="模拟 OpenMV 设备上报")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--token", default="openmv-device-2026")
    parser.add_argument("--img", default="")
    parser.add_argument("--frames", type=int, default=60)
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--report-every", type=int, default=4, dest="report_every")
    parser.add_argument("--reports", type=int, default=0)
    args = parser.parse_args()

    img_path = find_demo_image(args.img)
    if not img_path:
        print("找不到可用的演示图片，请用 --img 指定一张 jpg/png")
        return 1

    base_url = "http://%s:%d" % (args.host, args.port)
    device = Device(base_url, args.token)

    if device.health() != 200:
        print("后端没响应：%s 请先启动后端，或确认 --host / --port" % base_url)
        return 1

    with open(img_path, "rb") as f:
        raw = f.read()

    print("演示图：%s（%d 字节）" % (img_path, len(raw)))
    print("目标：%s，帧间隔 %.1f 秒，每 %d 帧上报一条" % (base_url, args.interval, args.report_every))
    print("-" * 56)

    frames = max(0, args.frames)
    frame_ok = frame_fail = 0
    report_ok = report_fail = 0

    try:
        for i in range(1, frames + 1):
            # 每次给图片尾部改几个字节，让 MJPEG 流的每帧内容都不同（否则浏览器可能复用缓存）
            payload = raw[:-8] + bytes([random.randint(1, 254) for _ in range(8)]) if len(raw) > 16 else raw
            code, msg = device.send_frame(payload)
            if code == 200:
                frame_ok += 1
            else:
                frame_fail += 1
                print("[帧 %d] 失败 %s %s" % (i, code, msg[:120]))

            if args.report_every and i % args.report_every == 0:
                fruit, result, conf, area = make_record()
                code, msg = device.send_report(fruit, result, conf, area, payload)
                if code == 201:
                    report_ok += 1
                    print("[上报 %d] %s / %s / %.3f / area=%d -> 201" % (report_ok, fruit, result, conf, area))
                else:
                    report_fail += 1
                    print("[上报] 失败 %s %s" % (code, msg[:120]))

            time.sleep(max(0.0, args.interval))

        # 补上报（frames=0 时常用）
        for _ in range(args.reports):
            fruit, result, conf, area = make_record()
            code, msg = device.send_report(fruit, result, conf, area, raw)
            if code == 201:
                report_ok += 1
                print("[上报 %d] %s / %s / %.3f / area=%d -> 201" % (report_ok, fruit, result, conf, area))
            else:
                report_fail += 1
                print("[上报] 失败 %s %s" % (code, msg[:120]))

    except KeyboardInterrupt:
        print("\n已手动停止")

    print("-" * 56)
    print("帧：成功 %d / 失败 %d；上报：成功 %d / 失败 %d" % (frame_ok, frame_fail, report_ok, report_fail))
    print("现在打开 http://localhost:5173 的看板，能看到画面刷新、统计变化、最近分拣滚动")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
