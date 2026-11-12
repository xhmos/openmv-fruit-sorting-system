# -*- coding: utf-8 -*-
"""
================================================================================
实验五 · 第 3 步 —— 轻量化 CNN 训练
================================================================================
对应实验报告 3.2 / 3.3：
    · 输入 96×96×3 RGB，像素归一化到 0~1
    · 3×3 卷积 + ReLU + 最大池化
    · Adam 优化器 + 交叉熵损失
    · Dropout + L2 正则抑制过拟合
    · 验证集准确率 ≥ 90% 作为收敛标准
    · 记录关键参数（学习率、迭代次数、batch size）

用法：
    # 默认：自建轻量 CNN，96×96，30 轮
    train_env\\Scripts\\python.exe train\\train_cnn.py

    # 用 MobileNetV2（alpha=0.35）做迁移学习
    train_env\\Scripts\\python.exe train\\train_cnn.py --arch mobilenet

    # 改输入尺寸 / 轮数 / 学习率
    train_env\\Scripts\\python.exe train\\train_cnn.py --img-size 96 --epochs 50 --lr 0.0005

产出：
    models\\fruit_cnn.keras        训练好的模型
    models\\class_names.json       类别顺序（板端 labels.txt 以此为准）
    models\\metrics.json           评估指标：准确率、混淆矩阵、每类指标、推理耗时
    models\\training_log.csv       每轮 loss/accuracy 记录
    models\\training_curve.png     训练曲线
================================================================================
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")

import numpy as np                                  # noqa: E402
import tensorflow as tf                             # noqa: E402
from tensorflow import keras                        # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SPLIT = ROOT / "dataset" / "split"
DEFAULT_MODELS = ROOT / "models"
IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def setup_console():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def count_images(d: Path):
    """递归统计图片数量（split/train 下面是类别子目录）。"""
    if not d.exists():
        return 0
    return sum(1 for f in d.rglob("*") if f.is_file() and f.suffix.lower() in IMG_EXTS)


# ------------------------------------------------------------------------------
# 模型
# ------------------------------------------------------------------------------
def build_simple_cnn(num_classes, img_size, l2=1e-4, dropout=0.3):
    """
    自建轻量 CNN（MicroNet 风格）。
    参数量约 6 万，INT8 量化后 200KB 上下，OpenMV H7 也能放得下。

    结构：Conv(16)-Pool → Conv(32)-Pool → Conv(64)-Pool → Conv(64)-GAP → Dense-softmax
    每个卷积都用 3×3 核 + ReLU + L2，符合报告 3.2 的描述。
    """
    inputs = keras.Input(shape=(img_size, img_size, 3), name="image")
    x = keras.layers.Rescaling(1.0 / 255.0, name="rescale")(inputs)   # 归一化到 0~1

    x = keras.layers.Conv2D(16, 3, padding="same", activation="relu",
                            kernel_regularizer=keras.regularizers.l2(l2))(x)
    x = keras.layers.MaxPooling2D(2)(x)

    x = keras.layers.Conv2D(32, 3, padding="same", activation="relu",
                            kernel_regularizer=keras.regularizers.l2(l2))(x)
    x = keras.layers.MaxPooling2D(2)(x)

    x = keras.layers.Conv2D(64, 3, padding="same", activation="relu",
                            kernel_regularizer=keras.regularizers.l2(l2))(x)
    x = keras.layers.MaxPooling2D(2)(x)

    x = keras.layers.Conv2D(64, 3, padding="same", activation="relu",
                            kernel_regularizer=keras.regularizers.l2(l2))(x)
    x = keras.layers.GlobalAveragePooling2D()(x)

    x = keras.layers.Dropout(dropout)(x)
    x = keras.layers.Dense(32, activation="relu",
                           kernel_regularizer=keras.regularizers.l2(l2))(x)
    x = keras.layers.Dropout(dropout * 0.6)(x)
    outputs = keras.layers.Dense(num_classes, activation="softmax", name="probs")(x)

    return keras.Model(inputs, outputs, name="fruit_cnn")


def build_mobilenet(num_classes, img_size, dropout=0.3, imagenet=False):
    """
    MobileNetV2（alpha=0.35）。
    imagenet=True 会尝试加载预训练权重（需要联网下载，国内可能失败），
    所以默认 False，从头训练；样本足够时效果也够用。
    """
    weights = "imagenet" if imagenet else None
    base = keras.applications.MobileNetV2(
        input_shape=(img_size, img_size, 3),
        alpha=0.35,
        include_top=False,
        weights=weights,
    )
    base.trainable = True

    inputs = keras.Input(shape=(img_size, img_size, 3), name="image")
    # MobileNetV2 自带 1/127.5 的缩放，直接喂 0~255
    x = base(inputs, training=False)
    x = keras.layers.GlobalAveragePooling2D()(x)
    x = keras.layers.Dropout(dropout)(x)
    outputs = keras.layers.Dense(num_classes, activation="softmax", name="probs")(x)

    return keras.Model(inputs, outputs, name="mobilenet_fruit")


# ------------------------------------------------------------------------------
# 数据
# ------------------------------------------------------------------------------
def make_augmenter():
    """
    数据增强：随机翻转、旋转、缩放、亮度、对比度。
    放在 tf.data 管道里而不是模型里 —— 这样导出的模型干净，
    TFLite 转换不会因为增强层报不支持。
    """
    layers = keras.Sequential([
        keras.layers.RandomFlip("horizontal"),
        keras.layers.RandomRotation(0.10),
        keras.layers.RandomZoom(0.10),
    ], name="augment")

    def augment(images, labels):
        images = tf.cast(images, tf.float32)
        images = layers(images, training=True)
        images = tf.image.random_brightness(images, max_delta=0.15 * 255.0)
        images = tf.image.random_contrast(images, 0.85, 1.15)
        images = tf.clip_by_value(images, 0.0, 255.0)
        return images, labels

    return augment


def load_datasets(split_dir, img_size, batch, seed):
    """从 dataset/split 载入 train/val/test，返回 (ds, class_names, 各集数量)。"""
    train_dir = split_dir / "train"
    val_dir = split_dir / "val"
    test_dir = split_dir / "test"

    common = dict(
        labels="inferred",
        label_mode="int",
        image_size=(img_size, img_size),
        interpolation="bilinear",
    )

    train_ds = keras.utils.image_dataset_from_directory(
        train_dir, batch_size=batch, shuffle=True, seed=seed, **common
    )
    class_names = list(train_ds.class_names)

    # 验证集为空时（样本太少）退回用测试集，保证训练过程有监控指标
    if count_images(val_dir) > 0:
        val_ds = keras.utils.image_dataset_from_directory(
            val_dir, batch_size=batch, shuffle=False, **common
        )
    else:
        print("⚠ 验证集为空，改用测试集作为验证集")
        val_ds = keras.utils.image_dataset_from_directory(
            test_dir, batch_size=batch, shuffle=False, **common
        )

    test_ds = keras.utils.image_dataset_from_directory(
        test_dir, batch_size=batch, shuffle=False, **common
    )

    autotune = tf.data.AUTOTUNE
    augment = make_augmenter()
    train_ds = train_ds.map(augment, num_parallel_calls=autotune).prefetch(autotune)
    val_ds = val_ds.prefetch(autotune)
    test_ds = test_ds.prefetch(autotune)

    return train_ds, val_ds, test_ds, class_names


# ------------------------------------------------------------------------------
# 评估
# ------------------------------------------------------------------------------
def evaluate(model, test_ds, class_names, img_size):
    """算测试集准确率、混淆矩阵、每类指标，以及 PC 端单张推理耗时。"""
    from sklearn.metrics import classification_report, confusion_matrix

    y_true, y_pred = [], []
    for images, labels in test_ds:
        probs = model(images, training=False)
        y_pred.extend(np.argmax(probs.numpy(), axis=1).tolist())
        y_true.extend(labels.numpy().tolist())

    y_true = np.array(y_true)
    y_pred = np.array(y_pred)

    acc = float((y_true == y_pred).mean()) if len(y_true) else 0.0
    cm = confusion_matrix(y_true, y_pred, labels=list(range(len(class_names)))).tolist()
    report = classification_report(
        y_true, y_pred,
        labels=list(range(len(class_names))),
        target_names=class_names,
        output_dict=True,
        zero_division=0,
    )

    # 单张推理耗时（PC，仅供对照，板端会慢很多）
    sample = np.random.rand(1, img_size, img_size, 3).astype("float32") * 255.0
    model(sample, training=False)                    # 预热
    t0 = time.perf_counter()
    runs = 30
    for _ in range(runs):
        model(sample, training=False)
    t1 = time.perf_counter()
    latency_ms = (t1 - t0) / runs * 1000

    return {
        "test_accuracy": acc,
        "confusion_matrix": cm,
        "per_class": {k: v for k, v in report.items() if k in class_names},
        "macro_avg": report.get("macro avg", {}),
        "pc_latency_ms_per_image": round(latency_ms, 2),
        "test_samples": int(len(y_true)),
    }


def plot_curve(csv_path: Path, out_png: Path):
    """把 CSVLogger 的记录画成 loss/accuracy 双曲线。"""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib import rcParams
        rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
        rcParams["axes.unicode_minus"] = False
    except Exception:
        print("matplotlib 不可用，跳过训练曲线绘制")
        return False

    if not csv_path.exists():
        return False

    import csv
    epochs, loss, acc, vloss, vacc = [], [], [], [], []
    with open(csv_path, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            epochs.append(int(row["epoch"]) + 1)
            loss.append(float(row["loss"]))
            acc.append(float(row["accuracy"]))
            vloss.append(float(row.get("val_loss", "nan")))
            vacc.append(float(row.get("val_accuracy", "nan")))

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    axes[0].plot(epochs, loss, label="train loss", color="#2E7D32")
    axes[0].plot(epochs, vloss, label="val loss", color="#C62828", linestyle="--")
    axes[0].set_xlabel("epoch")
    axes[0].set_ylabel("loss")
    axes[0].set_title("损失曲线")
    axes[0].legend()
    axes[0].grid(alpha=0.3)

    axes[1].plot(epochs, acc, label="train acc", color="#2E7D32")
    axes[1].plot(epochs, vacc, label="val acc", color="#C62828", linestyle="--")
    axes[1].axhline(0.9, color="#1565C0", linestyle=":", label="目标 90%")
    axes[1].set_xlabel("epoch")
    axes[1].set_ylabel("accuracy")
    axes[1].set_title("准确率曲线")
    axes[1].legend()
    axes[1].grid(alpha=0.3)

    fig.tight_layout()
    fig.savefig(out_png, dpi=150)
    plt.close(fig)
    return True


# ------------------------------------------------------------------------------
# 主流程
# ------------------------------------------------------------------------------
def main():
    setup_console()

    ap = argparse.ArgumentParser(description="实验五 轻量 CNN 训练")
    ap.add_argument("--split", type=Path, default=DEFAULT_SPLIT, help="划分后的数据目录")
    ap.add_argument("--out", type=Path, default=DEFAULT_MODELS, help="模型输出目录")
    ap.add_argument("--img-size", type=int, default=96, help="模型输入边长，默认 96")
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--arch", choices=["simple", "mobilenet"], default="simple")
    ap.add_argument("--dropout", type=float, default=0.3)
    ap.add_argument("--l2", type=float, default=1e-4)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--imagenet", action="store_true",
                    help="mobilenet 时加载 ImageNet 预训练权重（需联网下载）")
    args = ap.parse_args()

    tf.random.set_seed(args.seed)
    np.random.seed(args.seed)

    split_dir = Path(args.split).expanduser().resolve()
    out_dir = Path(args.out).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    for sub in ("train", "test"):
        if count_images(split_dir / sub) == 0:
            raise SystemExit(
                f"{split_dir / sub} 里没有图片。\n"
                "请先依次执行：\n"
                "  1) train\\collect_dataset.py  采集\n"
                "  2) train\\split_dataset.py     划分"
            )

    print("=" * 70)
    print("实验五 · 轻量化 CNN 训练")
    print("=" * 70)
    print(f"数据目录 : {split_dir}")
    print(f"输出目录 : {out_dir}")
    print(f"模型结构 : {args.arch}")
    print(f"输入尺寸 : {args.img_size}×{args.img_size}×3")
    print(f"训练参数 : epochs={args.epochs} batch={args.batch} lr={args.lr} "
          f"dropout={args.dropout} l2={args.l2} seed={args.seed}")

    train_ds, val_ds, test_ds, class_names = load_datasets(
        split_dir, args.img_size, args.batch, args.seed
    )
    print(f"类别     : {class_names}（共 {len(class_names)} 类）")
    print(f"样本     : train={count_images(split_dir / 'train')} "
          f"val={count_images(split_dir / 'val')} test={count_images(split_dir / 'test')}")
    print("=" * 70)

    if len(class_names) < 2:
        raise SystemExit("只有一个类别，无法训练分类模型。请至少采集两类样本。")

    if args.arch == "simple":
        model = build_simple_cnn(len(class_names), args.img_size, args.l2, args.dropout)
    else:
        model = build_mobilenet(len(class_names), args.img_size, args.dropout, args.imagenet)

    model.compile(
        optimizer=keras.optimizers.Adam(learning_rate=args.lr),
        loss=keras.losses.SparseCategoricalCrossentropy(),
        metrics=["accuracy"],
    )
    model.summary()

    best_path = out_dir / "fruit_cnn.keras"
    log_csv = out_dir / "training_log.csv"

    callbacks = [
        keras.callbacks.ModelCheckpoint(
            filepath=str(best_path),
            monitor="val_accuracy",
            save_best_only=True,
            mode="max",
            verbose=1,
        ),
        keras.callbacks.EarlyStopping(
            monitor="val_accuracy", patience=10, mode="max",
            restore_best_weights=True, verbose=1,
        ),
        keras.callbacks.ReduceLROnPlateau(
            monitor="val_loss", factor=0.5, patience=3, min_lr=1e-6, verbose=1,
        ),
        keras.callbacks.CSVLogger(str(log_csv), separator=",", append=False),
    ]

    t0 = time.time()
    history = model.fit(
        train_ds,
        validation_data=val_ds,
        epochs=args.epochs,
        callbacks=callbacks,
        verbose=2,
    )
    train_seconds = time.time() - t0

    print("=" * 70)
    print(f"训练结束，用时 {train_seconds:.1f} 秒")

    # 加载最优权重再评估（EarlyStopping 已 restore，这里从文件重载更保险）
    if best_path.exists():
        model = keras.models.load_model(str(best_path))
        print(f"已载入最优权重：{best_path.name}")

    metrics = evaluate(model, test_ds, class_names, args.img_size)
    metrics.update({
        "arch": args.arch,
        "img_size": args.img_size,
        "epochs_planned": args.epochs,
        "epochs_ran": len(history.history.get("loss", [])),
        "batch": args.batch,
        "lr": args.lr,
        "dropout": args.dropout,
        "l2": args.l2,
        "seed": args.seed,
        "train_seconds": round(train_seconds, 1),
        "class_names": class_names,
        "train_samples": count_images(split_dir / "train"),
        "val_samples": count_images(split_dir / "val"),
        "test_samples_total": count_images(split_dir / "test"),
    })

    (out_dir / "class_names.json").write_text(
        json.dumps(class_names, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / "metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("-" * 70)
    print(f"测试集准确率 : {metrics['test_accuracy'] * 100:.2f}%")
    print(f"PC 单张推理  : {metrics['pc_latency_ms_per_image']} ms")
    print("-" * 70)
    print("各类指标：")
    for name in class_names:
        m = metrics["per_class"].get(name, {})
        if m:
            print(f"  {name:<12} precision={m.get('precision', 0):.3f} "
                  f"recall={m.get('recall', 0):.3f} f1={m.get('f1-score', 0):.3f}")
    print("-" * 70)
    print("混淆矩阵（行=真实，列=预测）：")
    for i, name in enumerate(class_names):
        row = metrics["confusion_matrix"][i]
        print(f"  {name:<12} {row}")

    if plot_curve(log_csv, out_dir / "training_curve.png"):
        print(f"训练曲线已保存：{out_dir / 'training_curve.png'}")

    acc = metrics["test_accuracy"]
    print("=" * 70)
    if acc >= 0.90:
        print(f"✅ 准确率 {acc * 100:.2f}% ≥ 90%，达到报告要求，可以进行模型转换")
    else:
        print(f"⚠ 准确率 {acc * 100:.2f}% < 90%，建议：")
        print("   · 每类样本补到 60 张以上，且覆盖更多角度/光照")
        print("   · 增加 --epochs 到 50，或把 --lr 降到 0.0005")
        print("   · 检查标签有没有标错（可以用 pc_infer.py 逐张看一眼）")
        print("   · 类别之间外观差异太小的话，考虑减少类别数")
    print(f"模型：{best_path}")
    print(f"指标：{out_dir / 'metrics.json'}")
    print("下一步：convert_tflite.py 转 .tflite 并做 INT8 量化")


if __name__ == "__main__":
    main()
