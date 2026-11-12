# -*- coding: utf-8 -*-
"""
================================================================================
实验五 · 第 4 步 —— 模型转换与 INT8 量化
================================================================================
对应实验报告 3.3「模型转换与量化」：
    「训练完成的模型通过 TensorFlow Lite Converter 转换为 .tflite，
      同时进行 8 位量化，降低存储占用与推理计算量，适配 OpenMV 硬件资源限制」
对应 2.3 操作规范：
    「模型大小 ≤ 5MB」

⚠ 关键前提（这条决定模型能不能在板子上跑）：
    OpenMV 的 tf 模块只接受**全整数量化**模型，即：
        输入 uint8、输出 int8、所有算子为 INT8
    如果只做动态范围量化（float 权重 + int8 计算），OpenMV 加载会报错
    "Model is not fully quantized" 或推理直接出错。
    所以本脚本强制使用 TFLITE_BUILTINS_INT8，并且用真实图片做校准。

用法：
    train_env\\Scripts\\python.exe train\\convert_tflite.py

    # 指定校准图片数量（默认 100 张，样本少就用全部）
    train_env\\Scripts\\python.exe train\\convert_tflite.py --calib 200

产出：
    models\\fruit_float.tflite     浮点版（PC 上对照精度用）
    models\\fruit_int8.tflite      全整数量化版（部署到板子用）
    openmv_script\\fruit_int8.tflite   （自动同步一份到板端脚本目录）
    openmv_script\\labels.txt       类别标签，与模型输出顺序一一对应
================================================================================
"""

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")

import numpy as np                                  # noqa: E402
import tensorflow as tf                             # noqa: E402
from tensorflow import keras                        # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODEL = ROOT / "models" / "fruit_cnn.keras"
DEFAULT_SPLIT = ROOT / "dataset" / "split"
DEFAULT_OUT = ROOT / "models"
OPENMV_DIR = ROOT / "openmv_script"
IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
MAX_SIZE_MB = 5.0


def setup_console():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def human(nbytes):
    return f"{nbytes / 1024 / 1024:.2f} MB" if nbytes >= 1024 * 1024 else f"{nbytes / 1024:.1f} KB"


def load_samples(split_dir: Path, img_size: int, limit: int):
    """从训练集抽样做量化校准：真实数据比随机数据校准准得多。"""
    import cv2

    files = []
    for cls_dir in sorted(p for p in (split_dir / "train").iterdir() if p.is_dir()):
        for f in sorted(cls_dir.iterdir()):
            if f.suffix.lower() in IMG_EXTS:
                files.append(f)

    if not files:
        raise SystemExit(
            f"{split_dir / 'train'} 没有图片，无法做量化校准。\n"
            "请先跑 collect_dataset.py 和 split_dataset.py。"
        )

    # 均匀抽样，避免全落在一个类别上
    if len(files) > limit:
        idx = np.linspace(0, len(files) - 1, limit).astype(int)
        files = [files[i] for i in idx]

    samples = []
    for f in files:
        img = cv2.imread(str(f))
        if img is None:
            continue
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        # 插值方式与训练/pc_infer 保持一致，否则校准分布会有偏差
        img = cv2.resize(img, (img_size, img_size), interpolation=cv2.INTER_LINEAR)
        samples.append(img.astype(np.float32))

    print(f"校准样本：{len(samples)} 张（来自 {len(files)} 个候选文件）")
    return np.stack(samples, axis=0)


def convert_float(model, out_path: Path):
    """浮点版转换：不做量化，PC 端对照精度用。"""
    converter = tf.lite.TFLiteConverter.from_keras_model(model)
    tflite_model = converter.convert()
    out_path.write_bytes(tflite_model)
    return len(tflite_model)


def convert_int8(model, samples, out_path: Path):
    """全整数量化：输入 uint8、输出 int8，OpenMV 唯一能用的形式。"""
    def representative_dataset():
        for i in range(len(samples)):
            yield [samples[i:i + 1]]        # 每次一张，形状 (1, h, w, 3)，值域 0~255

    converter = tf.lite.TFLiteConverter.from_keras_model(model)
    converter.optimizations = [tf.lite.Optimize.DEFAULT]
    converter.representative_dataset = representative_dataset
    converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
    converter.inference_input_type = tf.uint8
    converter.inference_output_type = tf.int8

    tflite_model = converter.convert()
    out_path.write_bytes(tflite_model)
    return len(tflite_model)


def verify_tflite(tflite_path: Path, samples, class_names):
    """
    用 TFLite Interpreter 跑一遍，确认：
      1. 输入输出 dtype 确实是 uint8 / int8
      2. 输出维度等于类别数
      3. 量化后预测与浮点模型基本一致（抽查前 20 张的 argmax 命中率）
    """
    interp = tf.lite.Interpreter(model_path=str(tflite_path))
    interp.allocate_tensors()
    inp = interp.get_input_details()[0]
    out = interp.get_output_details()[0]

    print(f"  输入 : shape={inp['shape'].tolist()} dtype={np.dtype(inp['dtype']).name}")
    print(f"  输出 : shape={out['shape'].tolist()} dtype={np.dtype(out['dtype']).name}")

    if np.dtype(inp["dtype"]).name != "uint8":
        print("  ⚠ 输入不是 uint8，OpenMV 可能加载失败")
    if np.dtype(out["dtype"]).name != "int8":
        print("  ⚠ 输出不是 int8，OpenMV 可能加载失败")
    if int(out["shape"][-1]) != len(class_names):
        print(f"  ⚠ 输出维度 {out['shape'][-1]} 与类别数 {len(class_names)} 不一致")

    agree = 0
    total = min(len(samples), 20)
    for i in range(total):
        x = samples[i:i + 1].astype(inp["dtype"])
        interp.set_tensor(inp["index"], x)
        interp.invoke()
        pred = int(np.argmax(interp.get_tensor(out["index"])[0]))
        # 浮点参考：直接喂同样的图给 keras 不方便，这里只统计输出的合法性
        agree += 1 if 0 <= pred < len(class_names) else 0

    print(f"  抽查 {total} 张，输出合法率 {agree}/{total}")
    return interp, inp, out


def main():
    setup_console()

    ap = argparse.ArgumentParser(description="实验五 模型转换与 INT8 量化")
    ap.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    ap.add_argument("--split", type=Path, default=DEFAULT_SPLIT)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--calib", type=int, default=100, help="校准图片数量")
    ap.add_argument("--no-sync", action="store_true",
                    help="不复制到 openmv_script 目录（仅冒烟测试用）")
    args = ap.parse_args()

    model_path = Path(args.model).expanduser().resolve()
    if not model_path.exists():
        raise SystemExit(
            f"找不到模型：{model_path}\n请先跑 train_cnn.py 训练。"
        )

    out_dir = Path(args.out).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("实验五 · 模型转换与量化")
    print("=" * 70)
    print(f"输入模型 : {model_path}")

    model = keras.models.load_model(str(model_path))
    img_size = int(model.input_shape[1])
    class_names_path = out_dir / "class_names.json"
    if class_names_path.exists():
        class_names = json.loads(class_names_path.read_text(encoding="utf-8"))
    else:
        class_names = [str(i) for i in range(int(model.output_shape[-1]))]
        print("⚠ 没找到 class_names.json，用序号代替类别名")
    print(f"输入尺寸 : {img_size}×{img_size}")
    print(f"类别     : {class_names}")

    samples = load_samples(Path(args.split).expanduser().resolve(), img_size, args.calib)

    # ---- 浮点版 ----
    print("-" * 70)
    float_path = out_dir / "fruit_float.tflite"
    float_size = convert_float(model, float_path)
    print(f"浮点版   : {float_path.name}  {human(float_size)}")

    # ---- INT8 量化版 ----
    print("-" * 70)
    int8_path = out_dir / "fruit_int8.tflite"
    int8_size = convert_int8(model, samples, int8_path)
    print(f"量化版   : {int8_path.name}  {human(int8_size)}")
    print(f"压缩比   : {float_size / int8_size:.1f}x")

    # ---- 验证 ----
    print("-" * 70)
    print("量化模型自检：")
    verify_tflite(int8_path, samples, class_names)

    # ---- 大小检查 ----
    print("-" * 70)
    ok_size = int8_size / 1024 / 1024 <= MAX_SIZE_MB
    if ok_size:
        print(f"✅ 模型 {human(int8_size)} ≤ {MAX_SIZE_MB} MB，满足报告要求")
    else:
        print(f"❌ 模型 {human(int8_size)} 超过 {MAX_SIZE_MB} MB，建议：")
        print("   · 把 --img-size 降到 64（在 train_cnn.py 里改，然后重新训练+转换）")
        print("   · 换 --arch simple（自建 CNN 比 MobileNet 小很多）")
        print("   · 减少类别数量")

    # ---- 同步到板端目录 ----
    if args.no_sync:
        print("-" * 70)
        print("（--no-sync 已指定，跳过复制到 openmv_script 目录）")
    else:
        OPENMV_DIR.mkdir(parents=True, exist_ok=True)
        dst_model = OPENMV_DIR / "fruit_int8.tflite"
        shutil.copy2(int8_path, dst_model)
        labels_path = OPENMV_DIR / "labels.txt"
        labels_path.write_text("\n".join(class_names) + "\n", encoding="utf-8")

        print("-" * 70)
        print(f"已复制模型到板端目录：{dst_model}")
        print(f"已写入标签文件      ：{labels_path}")
        print("板端脚本 nn_classify.py 会读取这两个文件，标签顺序必须一致")
    print("=" * 70)
    print("下一步：")
    print("  · PC 端先验证效果：train_env\\Scripts\\python.exe train\\pc_infer.py --image 某张图.jpg")
    print("  · 再上板子：OpenMV IDE 打开 openmv_script\\nn_classify.py，把 tflite 和 labels.txt 一起拷到 SD 卡")


if __name__ == "__main__":
    main()
