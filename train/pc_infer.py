# -*- coding: utf-8 -*-
"""
================================================================================
实验五 · 第 5 步 —— PC 端推理验证
================================================================================
作用：在**上板之前**先用电脑把量化模型跑一遍，确认三件事
    1. 模型能正常加载（dtype、shape 对得上）
    2. 分类结果是否合理（别出现「全判成 apple」这种退化）
    3. 单张耗时大概多少（PC 上的数字仅供参考，板端会慢 5~20 倍）

这也是报告 3.3 第 4 点写的「调用 tf.lite.Interpreter 进行推理」的正确对象 ——
Interpreter 是 **PC 端** API；OpenMV 板子上用的是 tf.load() / tf.classify()，
两者不能混为一谈（这是原文档里的一处常见错误）。

用法：
    # 单张图片
    train_env\\Scripts\\python.exe train\\pc_infer.py --image dataset\\raw\\apple\\apple_0001.jpg

    # 摄像头实时预览（按 q 退出）
    train_env\\Scripts\\python.exe train\\pc_infer.py

    # 顺便把结果上报给后端（模拟板子上报，看板会实时刷新）
    train_env\\Scripts\\python.exe train\\pc_infer.py --report --server http://127.0.0.1:5000
================================================================================
"""

import argparse
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")

import numpy as np                                  # noqa: E402
import tensorflow as tf                             # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODEL = ROOT / "models" / "fruit_int8.tflite"
DEFAULT_LABELS = ROOT / "models" / "class_names.json"
DEVICE_TOKEN = "openmv-device-2026"


def setup_console():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


class TFLiteClassifier:
    """把 TFLite 的量化输入输出封装成一个好用的分类器。"""

    def __init__(self, model_path: Path, labels):
        self.interp = tf.lite.Interpreter(model_path=str(model_path))
        self.interp.allocate_tensors()
        self.inp = self.interp.get_input_details()[0]
        self.out = self.interp.get_output_details()[0]
        self.labels = labels

        self.in_dtype = np.dtype(self.inp["dtype"])
        self.out_dtype = np.dtype(self.out["dtype"])
        self.in_h = int(self.inp["shape"][1])
        self.in_w = int(self.inp["shape"][2])
        self.out_scale, self.out_zero = self.out["quantization"]

    def preprocess(self, bgr):
        """
        BGR → RGB、直接拉伸到模型输入尺寸、扩成 batch=1。

        ⚠ 这里**不能做居中裁剪**。训练时 image_dataset_from_directory 用的是
        tf.image.resize（直接拉伸、不裁比例），OpenMV 的 tf.classify 也是整图拉伸。
        如果这里先居中裁剪再缩放，PC 端和板端看到的画面构图就不一样，
        同一张图会得出不同结论 —— 这个坑很隐蔽，表现是「PC 上准、上板就乱」。
        插值用 INTER_LINEAR，与训练的 bilinear 保持一致。
        """
        import cv2

        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        rgb = cv2.resize(rgb, (self.in_w, self.in_h), interpolation=cv2.INTER_LINEAR)
        x = rgb[np.newaxis, ...]
        return x.astype(self.in_dtype if self.in_dtype != np.float32 else np.float32)

    def predict(self, bgr):
        """返回 (类别名, 置信度, 全部概率数组, 耗时ms)。"""
        x = self.preprocess(bgr)
        self.interp.set_tensor(self.inp["index"], x)
        t0 = time.perf_counter()
        self.interp.invoke()
        t1 = time.perf_counter()

        raw = self.interp.get_tensor(self.out["index"])[0]
        if self.out_dtype != np.float32 and self.out_scale:
            probs = (raw.astype(np.float32) - self.out_zero) * self.out_scale
        else:
            probs = raw.astype(np.float32)

        idx = int(np.argmax(probs))
        conf = float(probs[idx])
        name = self.labels[idx] if idx < len(self.labels) else str(idx)
        return name, conf, probs, (t1 - t0) * 1000


def report_to_backend(server, image_path, name, conf, area, timeout=8):
    """把一次识别结果推给后端，模拟板子上报，看板会实时出现这条记录。"""
    try:
        import requests
    except ImportError:
        print("  ⚠ 没装 requests，跳过上报")
        return False

    url = server.rstrip("/") + "/api/device/report"
    try:
        with open(image_path, "rb") as f:
            files = {"image": (Path(image_path).name, f, "image/jpeg")}
            data = {
                "fruit_type": name,
                "result": "good" if conf >= 0.6 else "bad",
                "confidence": f"{conf:.3f}",
                "area": str(area),
            }
            r = requests.post(url, data=data, files=files,
                              headers={"X-Device-Token": DEVICE_TOKEN}, timeout=timeout)
        ok = r.status_code in (200, 201)
        print(f"  上报{'成功' if ok else '失败'}：HTTP {r.status_code} {r.text[:120]}")
        return ok
    except Exception as exc:
        print(f"  上报异常：{exc}")
        return False


def infer_single(clf, image_path, topk=3, do_report=False, server=None):
    import cv2

    img = cv2.imread(str(image_path))
    if img is None:
        raise SystemExit(f"读不出图片：{image_path}")

    name, conf, probs, ms = clf.predict(img)

    print("=" * 60)
    print(f"图片：{image_path}")
    print(f"尺寸：{img.shape[1]}×{img.shape[0]}")
    print(f"推理：{ms:.1f} ms")
    print("-" * 60)

    order = np.argsort(probs)[::-1][:topk]
    for rank, i in enumerate(order, 1):
        label = clf.labels[i] if i < len(clf.labels) else str(i)
        bar = "█" * int(float(probs[i]) * 30)
        print(f"  {rank}. {label:<12} {float(probs[i]) * 100:6.2f}%  {bar}")

    print("-" * 60)
    print(f"结论：{name}（置信度 {conf * 100:.2f}%）")

    if float(probs[order[0]]) < 0.5:
        print("⚠ 最高置信度不足 50%，说明模型对这张图没把握：")
        print("   · 可能这张图的形态/光照跟训练集差太远")
        print("   · 也可能它根本不属于这三类")

    # 保存一张标注图，方便写报告
    out_img = img.copy()
    h, w = out_img.shape[:2]
    cv2.rectangle(out_img, (0, 0), (w - 1, 34), (255, 255, 255), -1)
    cv2.putText(out_img, f"{name} {conf * 100:.1f}%  {ms:.1f}ms",
                (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)
    out_path = Path(image_path).with_name(Path(image_path).stem + "_pred.jpg")
    cv2.imwrite(str(out_path), out_img)
    print(f"标注图：{out_path}")

    if do_report:
        report_to_backend(server or "http://127.0.0.1:5000", image_path, name, conf, int(w * h * 0.3))
    print("=" * 60)


def infer_camera(clf, camera_index, do_report=False, server=None):
    import cv2

    cap = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
    if not cap.isOpened():
        cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        raise SystemExit(
            f"打不开摄像头 {camera_index}。可能被后端 camera_service 占用，先停掉它再试。"
        )

    win = "pc_infer  (q quit)"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(win, 640, 480)

    fps = 0.0
    last = time.time()
    frame_no = 0
    last_report = 0.0

    print("摄像头推理已启动，按 q 退出")
    print("-" * 60)

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break

            name, conf, probs, ms = clf.predict(frame)
            frame_no += 1

            now = time.time()
            if now - last >= 1.0:
                fps = frame_no / (now - last)
                frame_no = 0
                last = now

            color = (0, 200, 0) if conf >= 0.6 else (0, 140, 255)
            cv2.rectangle(frame, (0, 0), (frame.shape[1] - 1, 32), (255, 255, 255), -1)
            cv2.putText(frame, f"{name} {conf * 100:.1f}%  {ms:.1f}ms  {fps:.1f}fps",
                        (8, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

            # 右侧画概率条
            y = 46
            for i, p in enumerate(probs):
                label = clf.labels[i] if i < len(clf.labels) else str(i)
                bar_w = int(float(p) * 120)
                cv2.rectangle(frame, (frame.shape[1] - 140, y),
                              (frame.shape[1] - 140 + bar_w, y + 12), (200, 200, 0), -1)
                cv2.putText(frame, f"{label}", (frame.shape[1] - 138, y + 11),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 0, 0), 1)
                y += 18

            cv2.imshow(win, frame)
            if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                break

            # 可选：每 3 秒上报一次，模拟板子推数据到后端看板
            if do_report and (now - last_report) > 3.0:
                last_report = now
                tmp = ROOT / "models" / "_last_capture.jpg"
                cv2.imwrite(str(tmp), frame)
                report_to_backend(server or "http://127.0.0.1:5000", tmp, name, conf,
                                  int(frame.shape[0] * frame.shape[1] * 0.3))
    finally:
        cap.release()
        cv2.destroyAllWindows()


def main():
    setup_console()

    ap = argparse.ArgumentParser(description="PC 端 TFLite 推理验证")
    ap.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    ap.add_argument("--labels", type=Path, default=DEFAULT_LABELS)
    ap.add_argument("--image", default=None, help="单张图片路径；不填则打开摄像头")
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--topk", type=int, default=3)
    ap.add_argument("--report", action="store_true", help="把结果上报给后端")
    ap.add_argument("--server", default="http://127.0.0.1:5000")
    args = ap.parse_args()

    model_path = Path(args.model).expanduser().resolve()
    if not model_path.exists():
        raise SystemExit(
            f"找不到模型：{model_path}\n请先跑 convert_tflite.py 生成 .tflite。"
        )

    labels_path = Path(args.labels).expanduser().resolve()
    if labels_path.exists() and labels_path.suffix == ".json":
        import json
        labels = json.loads(labels_path.read_text(encoding="utf-8"))
    elif labels_path.exists():
        labels = [l.strip() for l in labels_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    else:
        labels = ["class_%d" % i for i in range(8)]
        print("⚠ 没找到标签文件，用序号代替")

    clf = TFLiteClassifier(model_path, labels)
    print("=" * 60)
    print(f"模型  : {model_path.name}")
    print(f"输入  : {clf.in_h}×{clf.in_w}, {clf.in_dtype}")
    print(f"输出  : {int(clf.out['shape'][-1])} 类, {clf.out_dtype}")
    print(f"类别  : {labels}")
    print("=" * 60)

    if args.image:
        infer_single(clf, args.image, args.topk, args.report, args.server)
    else:
        infer_camera(clf, args.camera, args.report, args.server)


if __name__ == "__main__":
    main()
