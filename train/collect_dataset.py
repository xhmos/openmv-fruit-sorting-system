# -*- coding: utf-8 -*-
"""
================================================================================
实验五 · 第 1 步 —— 数据集采集
================================================================================
对应实验报告 2.3 操作规范：
    「采集图像数量不少于 200 张，每类目标图像数量不低于 50 张，
      分辨率统一为 320×240 或更低」

本脚本解决两件事：
    1. 用电脑摄像头现场拍，按类别分目录存放，统一缩放到 320×240
    2. 把已有的图片批量导入、统一尺寸后归档（避免手动改名）

输出目录结构：
    dataset/raw/
        apple/   apple_0001.jpg  apple_0002.jpg ...
        orange/  orange_0001.jpg ...
        banana/  banana_0001.jpg ...

用法（在项目根目录执行）：
    # 摄像头采集（默认类别 apple，按 0/1/2 切类，空格存图，q 退出）
    train_env\\Scripts\\python.exe train\\collect_dataset.py

    # 指定摄像头编号与目标尺寸
    train_env\\Scripts\\python.exe train\\collect_dataset.py --camera 1 --width 320 --height 240

    # 每类目标 60 张，采满自动提示
    train_env\\Scripts\\python.exe train\\collect_dataset.py --per-class 60

    # 把一批已有图片导入（--from 指向含子目录的文件夹，子目录名就是类别）
    train_env\\Scripts\\python.exe train\\collect_dataset.py --source import --from D:\\photos

    # 平铺图片全部归到某一类
    train_env\\Scripts\\python.exe train\\collect_dataset.py --source import --from D:\\photos --class apple

采集要点（报告里可以写进「实验步骤」）：
    · 光照稳定：关掉顶灯直射，用侧光或漫射光，避免高光过曝
    · 背景单一：用纯色桌面/纸板，减少与目标颜色接近的干扰
    · 每类至少覆盖：正视、侧视、不同距离、轻微遮挡，样本多样性比数量更重要
    · 三类样本数量尽量均衡，否则模型会偏向样本多的那一类
================================================================================
"""

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RAW = ROOT / "dataset" / "raw"
DEFAULT_CLASSES_FILE = Path(__file__).resolve().parent / "classes.txt"

IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def setup_console():
    """Windows 控制台默认 GBK，中文日志会乱码，这里强制 UTF-8。"""
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def load_classes(path):
    """读类别清单：每行一个，忽略空行与 # 注释。"""
    if not path.exists():
        raise SystemExit(
            f"找不到类别清单：{path}\n请先创建该文件，每行写一个类别名。"
        )
    classes = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        classes.append(line)
    if not classes:
        raise SystemExit(f"类别清单为空：{path}")
    return classes


def next_index(class_dir, class_name):
    """扫描已有文件，算出下一个可用编号，避免重名覆盖。"""
    if not class_dir.exists():
        return 1
    max_no = 0
    for f in class_dir.iterdir():
        if f.suffix.lower() not in IMG_EXTS:
            continue
        stem = f.stem
        # 期望形如 apple_0012
        if "_" not in stem:
            continue
        tail = stem.rsplit("_", 1)[-1]
        if tail.isdigit():
            max_no = max(max_no, int(tail))
    return max_no + 1


def count_images(class_dir):
    if not class_dir.exists():
        return 0
    return sum(1 for f in class_dir.iterdir() if f.suffix.lower() in IMG_EXTS)


def center_crop_resize(frame, width, height):
    """
    先按目标比例居中裁剪，再缩放到目标尺寸。
    直接 resize 会把果实拉扁，形态特征就废了。
    """
    import cv2

    src_h, src_w = frame.shape[:2]
    target_ratio = width / height
    src_ratio = src_w / src_h

    if src_ratio > target_ratio:
        # 原图偏宽，裁掉左右
        new_w = int(src_h * target_ratio)
        x0 = (src_w - new_w) // 2
        frame = frame[:, x0:x0 + new_w]
    else:
        # 原图偏高，裁掉上下
        new_h = int(src_w / target_ratio)
        y0 = (src_h - new_h) // 2
        frame = frame[y0:y0 + new_h, :]

    return cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)


def save_frame(frame, class_name, raw_dir, width, height):
    """存一张图并返回落盘路径。"""
    import cv2

    class_dir = raw_dir / class_name
    class_dir.mkdir(parents=True, exist_ok=True)
    idx = next_index(class_dir, class_name)
    path = class_dir / f"{class_name}_{idx:04d}.jpg"
    ok = cv2.imwrite(str(path), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
    if not ok:
        raise RuntimeError(f"写入失败：{path}")
    return path


# ------------------------------------------------------------------------------
# 模式一：摄像头现场采集
# ------------------------------------------------------------------------------
def run_camera(args, classes, raw_dir):
    try:
        import cv2
    except ImportError:
        raise SystemExit(
            "缺少 opencv-python。请先执行：\n"
            "  train_env\\Scripts\\python.exe -m pip install opencv-python -i https://pypi.tuna.tsinghua.edu.cn/simple"
        )

    cap = cv2.VideoCapture(args.camera, cv2.CAP_DSHOW)   # Windows 上 DSHOW 起流最快
    if not cap.isOpened():
        cap = cv2.VideoCapture(args.camera)              # 退回默认后端再试一次
    if not cap.isOpened():
        raise SystemExit(
            f"打不开摄像头 index={args.camera}。\n"
            "两种常见原因：\n"
            "  1. 摄像头被别的程序占用（比如后端 camera_service 正在采集），先停掉它\n"
            "  2. 编号不对，用 --camera 0/1/2 逐个试"
        )

    win = "collect dataset  (0-9 switch class / SPACE shoot / a auto / q quit)"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(win, args.width * 2, args.height * 2)

    current = 0
    auto_on = False
    last_auto = 0.0
    counts = {c: count_images(raw_dir / c) for c in classes}

    print("=" * 66)
    print("摄像头采集已启动")
    for i, c in enumerate(classes):
        print(f"  [{i}] {c}  已有 {counts[c]} 张")
    print(f"  目标尺寸 {args.width}×{args.height}，每类目标 {args.per_class} 张")
    print("按键：0-9 切类别 / 空格 拍一张 / a 自动连拍 / q 退出")
    print("=" * 66)

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("读帧失败，摄像头可能掉线了")
                break

            frame = center_crop_resize(frame, args.width, args.height)
            view = frame.copy()

            cls = classes[current]
            n = counts.get(cls, 0)
            ratio = n / args.per_class if args.per_class else 0

            color = (0, 200, 0) if ratio < 1 else (0, 140, 255)
            cv2.putText(view, f"class: {cls}  {n}/{args.per_class}",
                        (6, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)
            mode_txt = "AUTO" if auto_on else "MANUAL"
            cv2.putText(view, mode_txt, (6, args.height - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 200, 255), 1)
            cv2.imshow(win, view)

            key = cv2.waitKey(1) & 0xFF
            shoot = False

            if key == ord("q") or key == 27:
                break
            elif ord("0") <= key <= ord("9"):
                idx = key - ord("0")
                if idx < len(classes):
                    current = idx
                    print(f"→ 切换类别：{classes[current]}")
            elif key == ord(" "):
                shoot = True
            elif key == ord("a"):
                auto_on = not auto_on
                print(f"→ 自动连拍 {'开启' if auto_on else '关闭'}")

            # 自动模式：每 0.45 秒存一张，达到目标张数自动停
            if auto_on and (time_now() - last_auto) > 0.45:
                if counts.get(cls, 0) < args.per_class:
                    shoot = True
                    last_auto = time_now()
                else:
                    auto_on = False
                    print(f"→ {cls} 已达 {args.per_class} 张，自动连拍停止")

            if shoot:
                if counts.get(cls, 0) >= args.per_class:
                    print(f"  {cls} 已满 {args.per_class} 张，按 0-9 换类或调大 --per-class")
                    continue
                path = save_frame(frame, cls, raw_dir, args.width, args.height)
                counts[cls] = counts.get(cls, 0) + 1
                print(f"  已保存 [{cls}] {counts[cls]}/{args.per_class}  {path.name}")
    finally:
        cap.release()
        cv2.destroyAllWindows()

    print("=" * 66)
    print("采集结束，当前各类数量：")
    total = 0
    for c in classes:
        n = count_images(raw_dir / c)
        total += n
        flag = "OK" if n >= args.per_class else "不足"
        print(f"  {c:<12} {n:>4} 张   [{flag}]")
    print(f"  合计 {total} 张")
    if total >= 200:
        print("  总数已满足报告要求（≥200 张）")
    else:
        print(f"  距 200 张还差 {200 - total} 张，建议继续采集")


def time_now():
    import time
    return time.time()


# ------------------------------------------------------------------------------
# 模式二：导入已有图片
# ------------------------------------------------------------------------------
def run_import(args, classes, raw_dir):
    try:
        import cv2
    except ImportError:
        raise SystemExit("缺少 opencv-python，无法做缩放处理")

    src = Path(args.from_dir).expanduser().resolve()
    if not src.exists():
        raise SystemExit(f"源目录不存在：{src}")

    sub_dirs = [d for d in src.iterdir() if d.is_dir()]
    if sub_dirs:
        groups = {d.name: sorted(p for p in d.iterdir() if p.suffix.lower() in IMG_EXTS) for d in sub_dirs}
    else:
        if not args.class_name:
            raise SystemExit(
                "源目录是平铺的图片，需要用 --class 指定归属类别，例如 --class apple"
            )
        if args.class_name not in classes:
            raise SystemExit(f"--class {args.class_name} 不在类别清单里：{classes}")
        groups = {args.class_name: sorted(p for p in src.iterdir() if p.suffix.lower() in IMG_EXTS)}

    total = 0
    for cls, files in groups.items():
        if cls not in classes:
            print(f"跳过未知类别 {cls}（不在 classes.txt 里）")
            continue
        for f in files:
            if total and total % 50 == 0:
                print(f"  已处理 {total} 张 ...")
            img = cv2.imread(str(f))
            if img is None:
                print(f"  读不出，跳过：{f.name}")
                continue
            img = center_crop_resize(img, args.width, args.height)
            save_frame(img, cls, raw_dir, args.width, args.height)
            total += 1

    print("=" * 66)
    print(f"导入完成，共 {total} 张。当前各类数量：")
    for c in classes:
        print(f"  {c:<12} {count_images(raw_dir / c):>4} 张")


def main():
    setup_console()

    ap = argparse.ArgumentParser(description="实验五 数据集采集")
    ap.add_argument("--source", choices=["pc", "import"], default="pc",
                    help="pc=摄像头采集（默认）；import=导入已有图片")
    ap.add_argument("--camera", type=int, default=0, help="摄像头编号，默认 0")
    ap.add_argument("--width", type=int, default=320, help="保存宽度，默认 320")
    ap.add_argument("--height", type=int, default=240, help="保存高度，默认 240")
    ap.add_argument("--per-class", type=int, default=50, help="每类目标张数，默认 50")
    ap.add_argument("--classes-file", type=Path, default=DEFAULT_CLASSES_FILE, help="类别清单路径")
    ap.add_argument("--out", type=Path, default=DEFAULT_RAW, help="输出根目录")
    ap.add_argument("--from", dest="from_dir", default=None, help="import 模式的源目录")
    ap.add_argument("--class", dest="class_name", default=None, help="平铺导入时的归属类别")
    args = ap.parse_args()

    # 尺寸必须是 4 的倍数，否则 OpenMV 端 resize 会有偏差
    if args.width % 4 or args.height % 4:
        print("提示：宽高建议取 4 的倍数，已自动向下对齐")
        args.width = args.width - (args.width % 4)
        args.height = args.height - (args.height % 4)

    classes = load_classes(args.classes_file)
    raw_dir = Path(args.out).expanduser().resolve()
    raw_dir.mkdir(parents=True, exist_ok=True)

    print(f"类别：{classes}")
    print(f"输出：{raw_dir}")

    if args.source == "pc":
        run_camera(args, classes, raw_dir)
    else:
        if not args.from_dir:
            raise SystemExit("import 模式需要 --from 指定源目录")
        run_import(args, classes, raw_dir)


if __name__ == "__main__":
    main()
