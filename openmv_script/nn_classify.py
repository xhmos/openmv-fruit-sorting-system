# -*- coding: utf-8 -*-
"""
================================================================================
基于 OpenMV 的果实智能分拣 —— 板端神经网络推理脚本
================================================================================
文件位置：openmv_script\\nn_classify.py
运行环境：OpenMV IDE（MicroPython 固件 ≥ 4.5.0），型号 H7 Plus / RT1062 推荐

和 main.py 的区别：
    main.py       用 LAB 颜色阈值找色块，没有模型，属于「传统机器视觉」
    nn_classify.py 加载训练好的 .tflite，用神经网络分类，是实验五要求的做法

⚠ 关于 API（这是原实验文档里最容易写错的一处）：
    文档 3.3 第 4 点写「调用 OpenMV 的 AI 接口（如 tf.lite.Interpreter）」——
    这是错的。tf.lite.Interpreter 是 **PC 端 TensorFlow 的 API**，
    板子上没有这个东西。OpenMV 固件里的接口是：
        net = tf.load("model.tflite")     加载模型
        tf.classify(net, img)             分类推理
        tf.detect(net, img)               目标检测推理
    本脚本用的是正确的 tf.load / tf.classify。

⚠ 硬件前提：
    只有 **H7 Plus / RT1062（32MB SDRAM）** 放得下神经网络模型。
    标准 H7 只有 1MB SRAM，加载几 MB 的模型会直接 MemoryError。
    如果你手上是标准 H7，需要先换板或把模型压到极小（不太现实）。

使用步骤：
    1. 用 train\\convert_tflite.py 生成 fruit_int8.tflite 和 labels.txt
    2. 把这两个文件拷到 OpenMV 的 SD 卡根目录（或 Flash 的 /flash 目录）
    3. 在 OpenMV IDE 里打开本文件，点运行
    4. 首次运行会打印模型输入输出尺寸，确认无误后再现场调试

联网上报（NET_MODE）：
    "wlan" —— WiFi 扩展板直连后端
    "none" —— 不联网，只在 IDE 里看分类结果（调模型阶段用这个）
================================================================================
"""

import sensor
import image
import time
import os

try:
    import ujson as json
except ImportError:
    import json

try:
    import tf
except ImportError:
    raise SystemExit("当前固件没有 tf 模块。请把 OpenMV 固件升级到 4.5.0 以上。")


# ==============================================================================
# 一、必须改的配置
# ==============================================================================
MODEL_PATH = "fruit_int8.tflite"        # 模型文件名（放 SD 卡根目录）
LABELS_PATH = "labels.txt"              # 标签文件名，一行一个类别

NET_MODE = "none"                       # "wlan" / "none"

WIFI_SSID = "你的WiFi名"
WIFI_PASSWORD = "你的WiFi密码"

SERVER_HOST = "10.153.180.220"          # 后端电脑的局域网 IP
SERVER_PORT = 5000
DEVICE_TOKEN = "openmv-device-2026"

GOOD_CONFIDENCE = 0.65                  # 置信度达到多少判为「合格」
REPORT_COOLDOWN_MS = 2500               # 同一个目标最短重复上报间隔
FRAME_INTERVAL_MS = 800                 # 实时帧上传间隔（网页看板用）
SETTING_PULL_MS = 10000


_state = {
    "network_ready": False,
    "last_report_ms": 0,
    "last_frame_ms": 0,
    "last_pull_ms": 0,
    "ok_count": 0,
    "fail_count": 0,
}


# ==============================================================================
# 二、基础工具
# ==============================================================================
def log(msg):
    print("[nn] %s" % msg)


def ticks_now():
    return time.ticks_ms()


def elapsed(start_ms):
    return time.ticks_diff(ticks_now(), start_ms)


def load_labels(path):
    """逐行读标签文件。顺序必须和模型输出一致（转换脚本已经保证这一点）。"""
    labels = []
    try:
        with open(path, "r") as f:
            for line in f.readlines():
                line = line.strip()
                if line:
                    labels.append(line)
    except Exception as exc:
        log("读标签文件失败：%s（会用序号代替）" % exc)
    return labels


# ==============================================================================
# 三、HTTP（精简版，和 main.py 同一套手写实现）
# ==============================================================================
def http_status_line(resp):
    if not resp:
        return ""
    first = resp.split(b"\r\n", 1)[0]
    try:
        return first.decode()
    except Exception:
        return ""


def json_body(resp):
    if not resp:
        return {}
    parts = resp.split(b"\r\n\r\n", 1)
    if len(parts) != 2:
        return {}
    try:
        return json.loads(parts[1])
    except Exception:
        try:
            text = parts[1]
            return json.loads(text[text.index(b"{"):text.rindex(b"}") + 1])
        except Exception:
            return {}


def http_request(method, path, headers=None, body=None, timeout=8):
    if not _state["network_ready"]:
        return b""

    import socket
    headers = headers or []

    try:
        addr = (SERVER_HOST, SERVER_PORT)
        try:
            addr = socket.getaddrinfo(SERVER_HOST, SERVER_PORT)[0][-1]
        except Exception:
            pass

        s = socket.socket()
        s.settimeout(timeout)
        s.connect(addr)

        head = "%s %s HTTP/1.1\r\n" % (method, path)
        head += "Host: %s:%d\r\n" % (SERVER_HOST, SERVER_PORT)
        head += "Connection: close\r\n"
        for k, v in headers:
            head += "%s: %s\r\n" % (k, v)
        if body:
            head += "Content-Length: %d\r\n" % len(body)
        head += "\r\n"
        s.send(head.encode())

        if body:
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
            if len(data) > 8192:
                break

        try:
            s.close()
        except Exception:
            pass
        return data

    except Exception as exc:
        log("HTTP 失败 %s %s -> %s" % (method, path, exc))
        return b""


def build_multipart(fields, image_bytes=None, filename="shot.jpg"):
    boundary = "----OpenMVBoundary8f3c2a91"
    out = b""
    for key in fields:
        out += ("--%s\r\n" % boundary).encode()
        out += ('Content-Disposition: form-data; name="%s"\r\n\r\n' % key).encode()
        out += ("%s\r\n" % fields[key]).encode()
    if image_bytes:
        out += ("--%s\r\n" % boundary).encode()
        out += ('Content-Disposition: form-data; name="image"; filename="%s"\r\n' % filename).encode()
        out += b"Content-Type: image/jpeg\r\n\r\n"
        out += image_bytes
        out += b"\r\n"
    out += ("--%s--\r\n" % boundary).encode()
    return out, boundary


def capture_jpeg(img_obj, quality=70):
    for path in ("/ram/up_tmp.jpg", "/sd/up_tmp.jpg", "up_tmp.jpg"):
        try:
            try:
                img_obj.save(path, quality=quality)
            except Exception:
                img_obj.compress(quality=quality)
                img_obj.save(path)
        except Exception:
            continue
        try:
            with open(path, "rb") as f:
                data = f.read()
        except Exception:
            data = None
        try:
            os.remove(path)
        except Exception:
            pass
        if data:
            return data
    return None


def report_record(fruit_type, result, confidence, area, jpeg):
    fields = {
        "fruit_type": fruit_type,
        "result": result,
        "confidence": "%.3f" % confidence,
        "area": str(area),
    }
    body, boundary = build_multipart(fields, jpeg)
    headers = [
        ("Content-Type", "multipart/form-data; boundary=%s" % boundary),
        ("X-Device-Token", DEVICE_TOKEN),
    ]
    resp = http_request("POST", "/api/device/report", headers, body)
    if " 201 " in http_status_line(resp) or json_body(resp).get("code") == 0:
        _state["ok_count"] += 1
        log("上报成功 #%d  %s %s %.2f" % (_state["ok_count"], fruit_type, result, confidence))
        return True
    _state["fail_count"] += 1
    log("上报失败（%s）" % http_status_line(resp))
    return False


def upload_frame(jpeg):
    if not jpeg:
        return False
    body, boundary = build_multipart({}, jpeg, "frame.jpg")
    headers = [
        ("Content-Type", "multipart/form-data; boundary=%s" % boundary),
        ("X-Device-Token", DEVICE_TOKEN),
    ]
    return " 200 " in http_status_line(http_request("POST", "/api/device/frame", headers, body))


# ==============================================================================
# 四、联网
# ==============================================================================
def init_network():
    if NET_MODE == "none":
        log("NET_MODE=none，只分类不上报")
        return False

    import network
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        log("连接 WiFi：%s" % WIFI_SSID)
        wlan.connect(WIFI_SSID, WIFI_PASSWORD)
        deadline = ticks_now()
        while not wlan.isconnected() and elapsed(deadline) < 20000:
            time.sleep_ms(200)

    if wlan.isconnected():
        log("WiFi 已连接 IP=%s" % wlan.ifconfig()[0])
        _state["network_ready"] = True
        return True

    log("WiFi 失败：检查 SSID/密码，注意必须是 2.4G 频段")
    _state["network_ready"] = False
    return False


def ensure_network():
    if NET_MODE != "wlan":
        return _state["network_ready"]
    if _state["network_ready"]:
        return True
    return init_network()


# ==============================================================================
# 五、模型加载与推理
# ==============================================================================
def init_camera():
    """
    ⚠ 这里必须用 RGB565 + QVGA。
    神经网络模型是按 RGB 训练的，用 GRAYSCALE 会得到完全错误的结果。
    """
    sensor.reset()
    sensor.set_pixformat(sensor.RGB565)
    sensor.set_framesize(sensor.QVGA)       # 320×240
    sensor.set_auto_gain(False)
    sensor.set_auto_whitebal(False)
    sensor.skip_frames(time=2000)
    log("摄像头就绪 QVGA RGB565")


def init_model():
    """
    load_to_fb=True 把模型直接放帧缓冲区内存里，省下一半 RAM。
    H7 Plus 有 32MB SDRAM，放 1~2MB 的量化模型很轻松；
    标准 H7 只有 1MB SRAM，基本放不下，会 MemoryError。
    """
    log("加载模型 %s ..." % MODEL_PATH)
    try:
        net = tf.load(MODEL_PATH, load_to_fb=True)
    except Exception as exc:
        log("load_to_fb 失败（%s），回退到普通加载" % exc)
        net = tf.load(MODEL_PATH)

    log("模型加载完成")
    return net


def classify_best(net, img, labels):
    """
    返回 (类别名, 置信度, 框, 全部概率)。
    tf.classify 会做多尺度滑窗，返回多个候选；
    这里取「最大概率最高」的那一个，符合单果实入镜的场景。
    """
    try:
        results = tf.classify(net, img, min_scale=1.0, scale_mul=1.0,
                              x_overlap=0.0, y_overlap=0.0)
    except TypeError:
        # 部分固件不支持关键字参数，退回最简单的调用
        results = tf.classify(net, img)

    if not results:
        return None, 0.0, None, []

    best = None
    best_conf = -1.0
    for obj in results:
        probs = obj.output()
        if not probs:
            continue
        top = max(probs)
        if top > best_conf:
            best_conf = top
            best = obj

    if best is None:
        return None, 0.0, None, []

    probs = best.output()
    idx = 0
    top = probs[0]
    for i in range(len(probs)):
        if probs[i] > top:
            top = probs[i]
            idx = i

    name = labels[idx] if idx < len(labels) else "class_%d" % idx
    return name, float(top), best.rect(), probs


# ==============================================================================
# 六、主循环
# ==============================================================================
def main():
    labels = load_labels(LABELS_PATH)
    if not labels:
        log("⚠ 没有读到标签文件，类别会显示成 class_0/1/2")

    init_camera()
    net = init_model()

    if NET_MODE == "wlan":
        init_network()

    log("开始运行，Ctrl-C 停止")
    log("类别共 %d 个：%s" % (len(labels), labels))

    while True:
        img = sensor.snapshot()
        now = ticks_now()

        name, conf, rect, probs = classify_best(net, img, labels)

        need_report = False
        jpeg = None

        if name is not None:
            result = "good" if conf >= GOOD_CONFIDENCE else "bad"
            area = (rect[2] * rect[3]) if rect else (img.width() * img.height() // 3)

            color = (0, 255, 0) if result == "good" else (255, 0, 0)
            if rect:
                img.draw_rectangle(rect, color=color, thickness=2)
            img.draw_string(4, 4, "%s %.2f" % (name, conf), color=color, scale=2)

            # 概率条，方便现场看出模型有没有把握
            y = 28
            for i in range(len(probs)):
                label = labels[i] if i < len(labels) else "c%d" % i
                w = int(float(probs[i]) * 60)
                img.draw_rectangle(4, y, w, 6, color=(0, 180, 255), fill=True)
                img.draw_string(70, y - 2, label, color=(255, 255, 255), scale=1)
                y += 10

            if elapsed(_state["last_report_ms"]) > REPORT_COOLDOWN_MS:
                need_report = True
        else:
            img.draw_string(4, 4, "no object", color=(255, 255, 0), scale=2)

        # 只在需要发数据时编码 JPEG，省 CPU
        need_frame = elapsed(_state["last_frame_ms"]) > FRAME_INTERVAL_MS
        if need_report or need_frame:
            jpeg = capture_jpeg(img)

        if need_report and NET_MODE == "wlan":
            _state["last_report_ms"] = now
            ensure_network()
            report_record(name, result, conf, area, jpeg)

        if need_frame and jpeg and NET_MODE == "wlan":
            _state["last_frame_ms"] = now
            upload_frame(jpeg)

        time.sleep_ms(10)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("已停止")
        log("统计：成功 %d / 失败 %d" % (_state["ok_count"], _state["fail_count"]))
    except Exception as exc:
        log("异常退出：%s" % exc)
        raise
