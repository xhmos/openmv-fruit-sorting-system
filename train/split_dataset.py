# -*- coding: utf-8 -*-
"""
================================================================================
实验五 · 第 2 步 —— 数据集划分（7:2:1）
================================================================================
对应实验报告 3.3「数据集处理」：
    「按 7:2:1 比例划分为训练集、验证集与测试集」

输入：dataset/raw/<class>/*.jpg
输出：dataset/split/train|val|test/<class>/*.jpg
      dataset/split/manifest.json  （划分结果与统计，训练脚本会读）

用法：
    train_env\\Scripts\\python.exe train\\split_dataset.py
    train_env\\Scripts\\python.exe train\\split_dataset.py --train 0.7 --val 0.2 --test 0.1
    train_env\\Scripts\\python.exe train\\split_dataset.py --clean   （先清空旧划分再重划）

为什么要固定随机种子：
    每次重划结果一致，实验记录里的准确率才可比。改种子等于换了一次划分。
================================================================================
"""

import argparse
import json
import random
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RAW = ROOT / "dataset" / "raw"
DEFAULT_SPLIT = ROOT / "dataset" / "split"
IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def setup_console():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def collect(raw_dir):
    """按类别收集文件，返回 {类别: [文件...]}。"""
    groups = {}
    if not raw_dir.exists():
        raise SystemExit(f"原始数据目录不存在：{raw_dir}\n请先跑 collect_dataset.py 采集图片。")
    for d in sorted(p for p in raw_dir.iterdir() if p.is_dir()):
        files = sorted(p for p in d.iterdir() if p.suffix.lower() in IMG_EXTS)
        if files:
            groups[d.name] = files
    if not groups:
        raise SystemExit(f"{raw_dir} 下没有找到任何图片。")
    return groups


def main():
    setup_console()

    ap = argparse.ArgumentParser(description="按 7:2:1 划分数据集")
    ap.add_argument("--raw", type=Path, default=DEFAULT_RAW)
    ap.add_argument("--out", type=Path, default=DEFAULT_SPLIT)
    ap.add_argument("--train", type=float, default=0.7)
    ap.add_argument("--val", type=float, default=0.2)
    ap.add_argument("--test", type=float, default=0.1)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--clean", action="store_true", help="划分前清空输出目录")
    args = ap.parse_args()

    if abs(args.train + args.val + args.test - 1.0) > 1e-6:
        raise SystemExit("train + val + test 必须等于 1.0")

    raw_dir = Path(args.raw).expanduser().resolve()
    out_dir = Path(args.out).expanduser().resolve()

    if args.clean and out_dir.exists():
        for sub in ("train", "val", "test"):
            p = out_dir / sub
            if p.exists():
                shutil.rmtree(p)
        print(f"已清空旧划分：{out_dir}")

    groups = collect(raw_dir)
    rng = random.Random(args.seed)

    print("=" * 66)
    print(f"原始数据：{raw_dir}")
    print(f"输出目录：{out_dir}")
    print(f"比例 train={args.train} val={args.val} test={args.test} seed={args.seed}")
    print("=" * 66)

    manifest = {"seed": args.seed, "ratio": [args.train, args.val, args.test], "classes": {}}
    warnings = []

    for cls, files in groups.items():
        files = list(files)
        rng.shuffle(files)
        n = len(files)

        n_train = int(round(n * args.train))
        n_val = int(round(n * args.val))
        # 剩下的全给 test，保证总数不丢
        n_test = n - n_train - n_val

        # 样本太少时保证 val/test 至少各 1 张，否则评估没法算
        if n >= 3 and n_val == 0:
            n_val, n_train = 1, n_train - 1
        if n >= 3 and n_test == 0:
            n_test, n_train = 1, n_train - 1
        if n_train <= 0:
            warnings.append(f"{cls} 只有 {n} 张，不足以划分，全部进训练集")
            n_train, n_val, n_test = n, 0, 0

        splits = {
            "train": files[:n_train],
            "val": files[n_train:n_train + n_val],
            "test": files[n_train + n_val:n_train + n_val + n_test],
        }

        for sub, subset in splits.items():
            dst_dir = out_dir / sub / cls
            dst_dir.mkdir(parents=True, exist_ok=True)
            for src in subset:
                shutil.copy2(src, dst_dir / src.name)

        manifest["classes"][cls] = {
            "total": n,
            "train": len(splits["train"]),
            "val": len(splits["val"]),
            "test": len(splits["test"]),
        }
        print(f"{cls:<14} 总 {n:>3}  →  train {len(splits['train']):>3} / val {len(splits['val']):>2} / test {len(splits['test']):>2}")

    total = sum(v["total"] for v in manifest["classes"].values())
    manifest["total"] = total
    manifest["num_classes"] = len(manifest["classes"])

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("=" * 66)
    print(f"合计 {total} 张，{len(manifest['classes'])} 类")
    if total < 200:
        warnings.append(f"总样本 {total} 张，未达到报告要求的 ≥200 张")
    for w in warnings:
        print(f"  ⚠ {w}")
    print(f"划分清单已写入：{out_dir / 'manifest.json'}")
    print("下一步：train_cnn.py 开始训练（纯分类任务不需要先做 LabelImg 标注）")


if __name__ == "__main__":
    main()
