# -*- coding: utf-8 -*-
"""
模型训练管理：网页上传真实图片 -> 划分数据集 -> 训练 -> 转 TFLite。

为什么用子进程而不是 import：
    训练脚本装在 train_env 里（TensorFlow 2.21），后端跑在 backend/venv 里，
    两个环境互相独立，后端不能 import tensorflow。所以这里统一用
    train_env 的 python 以子进程方式调用 train/ 下的脚本。

状态怎么同步：
    Popen 启动后不阻塞 HTTP 请求，状态写在 models/.train_state.json，
    输出写到 models/.train.log，前端定时来查 /api/train/status 即可。
"""

import json
import os
import re
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

from flask import Blueprint, jsonify, request
from PIL import Image, ImageOps

from extensions import db
from config import Config
from utils.security import admin_required, login_required, write_operation_log

train_bp = Blueprint("train", __name__)

# ---------------------------------------------------------------- 路径常量
ROOT = Path(__file__).resolve().parent.parent.parent

RAW_DIR = ROOT / "dataset" / "raw"
SPLIT_DIR = ROOT / "dataset" / "split"
MODEL_DIR = ROOT / "models"
TRAIN_SCRIPT = ROOT / "train" / "train_cnn.py"
SPLIT_SCRIPT = ROOT / "train" / "split_dataset.py"
CONVERT_SCRIPT = ROOT / "train" / "convert_tflite.py"
CLASSES_FILE = ROOT / "train" / "classes.txt"
TRAIN_PY = ROOT / "train_env" / "Scripts" / "python.exe"

STATE_FILE = MODEL_DIR / ".train_state.json"
LOG_FILE = MODEL_DIR / ".train.log"

# 类别名只允许小写字母开头 + 字母/数字/下划线，长度 2~20
# 这个目录名会拼进文件路径，必须严格限制，避免 ../ 穿越
CLASS_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,19}$")

IMAGE_EXTS = {".jpg", ".jpeg", ".png"}

TARGET_W = 320
TARGET_H = 240

# 同一时间只允许一个训练/转换任务，避免两个进程抢同一个模型目录
_state_lock = threading.Lock()


# ---------------------------------------------------------------- 小工具
def _now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _read_classes():
    """读 classes.txt：跳过注释和空行，保持文件里的顺序（= 板端标签顺序）。"""
    if not CLASSES_FILE.exists():
        return []
    names = []
    for line in CLASSES_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if CLASS_NAME_RE.match(line):
            names.append(line)
    return names


def _count_images(folder: Path):
    """统计图片张数，兼容「平铺」和「子目录」两种结构。"""
    if not folder.exists():
        return 0
    total = 0
    for p in folder.rglob("*"):
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS:
            total += 1
    return total


def _sniff(head: bytes):
    """按文件头判断真实格式，防止改后缀绕过。"""
    if head.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    return None


def _tail_lines(path: Path, n=40):
    """只读文件尾部，避免几十 KB 的日志整份读进内存。"""
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            back = min(size, 12 * 1024)
            f.seek(size - back)
            raw = f.read()
        return raw.decode("utf-8", errors="replace").splitlines()[-n:]
    except Exception:
        return []


def _read_state():
    if not STATE_FILE.exists():
        return {"running": False, "stage": "idle"}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"running": False, "stage": "idle"}


def _write_state(state: dict):
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _train_env_ready():
    return TRAIN_PY.exists() and TRAIN_SCRIPT.exists()


def _child_env():
    """子进程环境：强制 UTF-8 输出，避免中文日志在重定向后变成乱码。"""
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
    env.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
    return env


def _popen(cmd, log_fp):
    """Windows 下隐藏控制台窗口；其他平台不用这个 flag。"""
    kwargs = {
        "cwd": str(ROOT),
        "stdout": log_fp,
        "stderr": subprocess.STDOUT,
        "env": _child_env(),
    }
    if os.name == "nt":
        kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
    return subprocess.Popen(cmd, **kwargs)


def _watch_process(proc, log_fp, stage):
    """后台线程：等子进程结束，把退出码和结果写回状态文件。"""
    code = proc.wait()
    try:
        log_fp.close()
    except Exception:
        pass

    with _state_lock:
        state = _read_state()
        state.update(
            running=False,
            stage=f"{stage}_done",
            exit_code=code,
            finished_at=_now_str(),
        )
        if code == 0:
            state["message"] = "完成"
            if (MODEL_DIR / "metrics.json").exists():
                try:
                    state["metrics"] = json.loads(
                        (MODEL_DIR / "metrics.json").read_text(encoding="utf-8")
                    )
                except Exception:
                    pass
        else:
            state["message"] = f"进程退出码 {code}，请看日志"
        _write_state(state)


def _summary():
    """数据集与训练环境总览，前端靠它渲染统计卡片和按钮可用状态。"""
    classes = _read_classes()

    rows = []
    for name in classes:
        rows.append({"name": name, "count": _count_images(RAW_DIR / name)})

    # classes.txt 之外的目录也列出来，避免用户以为图片丢了
    extra = []
    if RAW_DIR.exists():
        for d in sorted(RAW_DIR.iterdir()):
            if d.is_dir() and d.name not in classes:
                extra.append({"name": d.name, "count": _count_images(d)})

    total = sum(r["count"] for r in rows) + sum(r["count"] for r in extra)

    split_stat = {
        "train": _count_images(SPLIT_DIR / "train"),
        "val": _count_images(SPLIT_DIR / "val"),
        "test": _count_images(SPLIT_DIR / "test"),
    }

    # 至少要两类、且 train/test 都有图，才能训练
    non_empty_classes = len([r for r in rows if r["count"] > 0])
    can_train = (
        non_empty_classes >= 2
        and split_stat["train"] > 0
        and split_stat["test"] > 0
        and _train_env_ready()
    )

    warnings = []
    if not _train_env_ready():
        warnings.append("找不到 train_env 或训练脚本，无法在本机训练")
    if non_empty_classes < 2:
        warnings.append("至少需要两类样本才能训练分类模型")
    for r in rows:
        if 0 < r["count"] < 50:
            warnings.append(f"{r['name']} 只有 {r['count']} 张，建议补到 50 张以上")

    return {
        "classes": rows,
        "extra_classes": extra,
        "total": total,
        "split": split_stat,
        "can_train": can_train,
        "train_env_ready": _train_env_ready(),
        "warnings": warnings,
        "target_size": f"{TARGET_W}×{TARGET_H}",
    }


# ---------------------------------------------------------------- 1. 数据集总览
@train_bp.get("/dataset")
@login_required
def dataset_overview():
    return jsonify(code=0, msg="ok", data=_summary())


# ---------------------------------------------------------------- 2. 上传图片
@train_bp.post("/upload")
@admin_required
def upload_images():
    class_name = (request.form.get("class_name") or "").strip()
    if not CLASS_NAME_RE.match(class_name):
        return jsonify(code=400, msg="类别名不合法"), 400

    allowed = _read_classes()
    if class_name not in allowed:
        return jsonify(
            code=400,
            msg=f"类别 {class_name} 不在 classes.txt 里。要新增类别请先改 train/classes.txt",
        ), 400

    files = request.files.getlist("file")
    if not files:
        return jsonify(code=400, msg="没有收到图片文件"), 400
    if len(files) > 30:
        return jsonify(code=400, msg="一次最多上传 30 张"), 400

    folder = RAW_DIR / class_name
    folder.mkdir(parents=True, exist_ok=True)

    saved = 0
    failed = []

    for fs in files:
        name = fs.filename or "未命名"
        ext = os.path.splitext(name)[1].lower()
        if ext not in IMAGE_EXTS:
            failed.append({"name": name, "reason": "只支持 jpg / png"})
            continue

        data = fs.read()
        if not data:
            failed.append({"name": name, "reason": "文件为空"})
            continue
        if len(data) > Config.MAX_IMAGE_BYTES:
            failed.append({"name": name, "reason": "超过 2MB"})
            continue
        if _sniff(data[:16]) is None:
            failed.append({"name": name, "reason": "不是有效图片（疑似改后缀）"})
            continue

        # 统一转成 320×240 的 JPEG，和 collect_dataset.py 的输出规格一致
        try:
            import io

            img = Image.open(io.BytesIO(data))
            img = ImageOps.exif_transpose(img)  # 手机照片按 EXIF 摆正方向
            img = img.convert("RGB")
            img = img.resize((TARGET_W, TARGET_H), Image.BILINEAR)
        except Exception:
            failed.append({"name": name, "reason": "图片解析失败，可能已损坏"})
            continue

        with _state_lock:
            # 找到当前最大编号，往后递增，绝不覆盖已有样本
            max_idx = 0
            for p in folder.glob(f"{class_name}_*"):
                m = re.search(r"_(\d+)\.jpg$", p.name)
                if m:
                    max_idx = max(max_idx, int(m.group(1)))
            idx = max_idx + 1
            target = folder / f"{class_name}_{idx:04d}.jpg"
            try:
                img.save(target, "JPEG", quality=92)
            except Exception:
                failed.append({"name": name, "reason": "保存失败"})
                continue
        saved += 1

    if saved:
        write_operation_log(
            "上传训练样本", "dataset/raw", f"{class_name} +{saved} 张"
        )
        db.session.commit()

    return jsonify(
        code=0,
        msg=f"成功保存 {saved} 张" if saved else "没有图片保存成功",
        data={"saved": saved, "failed": failed, "dataset": _summary()},
    )


# ---------------------------------------------------------------- 3. 划分数据集
@train_bp.post("/split")
@admin_required
def split_dataset():
    state = _read_state()
    if state.get("running"):
        return jsonify(code=409, msg="有任务正在运行，请先等它结束"), 409

    if not SPLIT_SCRIPT.exists():
        return jsonify(code=500, msg="找不到 split_dataset.py"), 500

    total = _count_images(RAW_DIR)
    if total == 0:
        return jsonify(code=400, msg="dataset/raw 里还没有图片，请先上传"), 400

    try:
        proc = subprocess.run(
            [str(TRAIN_PY), str(SPLIT_SCRIPT), "--clean", "--seed", "42"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=_child_env(),
            timeout=180,
        )
    except subprocess.TimeoutExpired:
        return jsonify(code=500, msg="划分超时（180 秒），请检查图片数量是否过多"), 500
    except Exception as exc:
        return jsonify(code=500, msg=f"划分失败：{exc}"), 500

    out = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        return jsonify(
            code=500,
            msg="划分失败，请看下面的日志",
            data={"log": out[-2000:]},
        ), 500

    write_operation_log("划分数据集", "dataset/split", f"{total} 张")
    db.session.commit()

    return jsonify(
        code=0,
        msg="划分完成",
        data={"log": out[-2000:], "dataset": _summary()},
    )


# ---------------------------------------------------------------- 4. 开始训练
@train_bp.post("/start")
@admin_required
def start_training():
    state = _read_state()
    if state.get("running"):
        return jsonify(code=409, msg="已有训练任务在跑，请等它结束或先取消"), 409

    if not _train_env_ready():
        return jsonify(
            code=500, msg="找不到 train_env 或训练脚本，无法启动训练"
        ), 500

    payload = request.get_json(silent=True) or {}

    # 参数只允许在安全范围内，并且逐个转成 int 后再拼命令行（不走 shell）
    try:
        epochs = int(payload.get("epochs", 30))
        img_size = int(payload.get("img_size", 96))
        batch = int(payload.get("batch", 32))
    except (TypeError, ValueError):
        return jsonify(code=400, msg="epochs / img_size / batch 必须是整数"), 400

    if not 1 <= epochs <= 200:
        return jsonify(code=400, msg="epochs 取值范围 1~200"), 400
    if img_size not in (32, 48, 64, 96, 128, 160):
        return jsonify(code=400, msg="img_size 只支持 32/48/64/96/128/160"), 400
    if not 1 <= batch <= 128:
        return jsonify(code=400, msg="batch 取值范围 1~128"), 400

    arch = payload.get("arch", "simple")
    if arch not in ("simple", "mobilenet"):
        return jsonify(code=400, msg="arch 只支持 simple 或 mobilenet"), 400

    train_n = _count_images(SPLIT_DIR / "train")
    test_n = _count_images(SPLIT_DIR / "test")
    if train_n == 0 or test_n == 0:
        return jsonify(
            code=400, msg="dataset/split 里没有数据，请先点「划分数据集」"
        ), 400

    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    cmd = [
        str(TRAIN_PY),
        str(TRAIN_SCRIPT),
        "--epochs", str(epochs),
        "--img-size", str(img_size),
        "--batch", str(batch),
        "--arch", arch,
    ]

    try:
        log_fp = open(LOG_FILE, "w", encoding="utf-8", errors="replace")
        proc = _popen(cmd, log_fp)
    except Exception as exc:
        return jsonify(code=500, msg=f"启动训练失败：{exc}"), 500

    with _state_lock:
        _write_state({
            "running": True,
            "stage": "training",
            "pid": proc.pid,
            "started_at": _now_str(),
            "finished_at": None,
            "exit_code": None,
            "epochs": epochs,
            "img_size": img_size,
            "batch": batch,
            "arch": arch,
            "metrics": None,
            "message": "训练进行中",
        })

    threading.Thread(
        target=_watch_process, args=(proc, log_fp, "training"), daemon=True
    ).start()

    write_operation_log(
        "启动模型训练", "models",
        f"epochs={epochs} img={img_size} batch={batch} arch={arch}"
    )
    db.session.commit()

    return jsonify(
        code=0,
        msg=f"训练已启动（PID {proc.pid}）",
        data={"pid": proc.pid, "cmd": " ".join(cmd)},
    )


# ---------------------------------------------------------------- 5. 训练状态
@train_bp.get("/status")
@login_required
def training_status():
    state = _read_state()
    tail = _tail_lines(LOG_FILE, 40) if LOG_FILE.exists() else []

    # 从 "Epoch 3/30" 这种输出里解析当前进度
    epoch, total_epochs = None, state.get("epochs")
    for line in tail:
        m = re.search(r"Epoch\s+(\d+)/(\d+)", line)
        if m:
            epoch, total_epochs = int(m.group(1)), int(m.group(2))

    progress = 0
    if total_epochs and epoch:
        progress = round(epoch / total_epochs * 100)

    if not state.get("running") and (MODEL_DIR / "metrics.json").exists():
        if not state.get("metrics"):
            try:
                state["metrics"] = json.loads(
                    (MODEL_DIR / "metrics.json").read_text(encoding="utf-8")
                )
            except Exception:
                pass

    state.update(progress=progress, epoch=epoch, total_epochs=total_epochs, tail=tail)
    return jsonify(code=0, msg="ok", data=state)


# ---------------------------------------------------------------- 6. 取消任务
@train_bp.post("/cancel")
@admin_required
def cancel_training():
    state = _read_state()
    pid = state.get("pid")
    if not state.get("running") or not pid:
        return jsonify(code=400, msg="当前没有正在运行的任务"), 400

    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True, timeout=15,
                creationflags=0x08000000,
            )
        else:
            os.kill(pid, 9)
    except Exception as exc:
        return jsonify(code=500, msg=f"取消失败：{exc}"), 500

    with _state_lock:
        state = _read_state()
        state.update(
            running=False,
            stage="cancelled",
            exit_code=-1,
            finished_at=_now_str(),
            message="已被手动取消",
        )
        _write_state(state)

    write_operation_log("取消模型训练", "models", f"pid={pid}")
    db.session.commit()

    return jsonify(code=0, msg="已取消")


# ---------------------------------------------------------------- 7. 转 TFLite
@train_bp.post("/convert")
@admin_required
def convert_tflite():
    state = _read_state()
    if state.get("running"):
        return jsonify(code=409, msg="有任务正在运行，请先等它结束"), 409

    if not (MODEL_DIR / "fruit_cnn.keras").exists():
        return jsonify(code=400, msg="还没有训练好的模型，请先训练"), 400
    if not CONVERT_SCRIPT.exists():
        return jsonify(code=500, msg="找不到 convert_tflite.py"), 500

    try:
        payload = request.get_json(silent=True) or {}
        calib = int(payload.get("calib", 100))
    except (TypeError, ValueError):
        return jsonify(code=400, msg="calib 必须是整数"), 400
    if not 10 <= calib <= 300:
        return jsonify(code=400, msg="calib 取值范围 10~300"), 400

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    cmd = [str(TRAIN_PY), str(CONVERT_SCRIPT), "--calib", str(calib)]

    try:
        log_fp = open(LOG_FILE, "w", encoding="utf-8", errors="replace")
        proc = _popen(cmd, log_fp)
    except Exception as exc:
        return jsonify(code=500, msg=f"启动转换失败：{exc}"), 500

    with _state_lock:
        _write_state({
            "running": True,
            "stage": "converting",
            "pid": proc.pid,
            "started_at": _now_str(),
            "finished_at": None,
            "exit_code": None,
            "epochs": None,
            "message": "正在量化转换",
        })

    threading.Thread(
        target=_watch_process, args=(proc, log_fp, "converting"), daemon=True
    ).start()

    write_operation_log("转换 TFLite 模型", "models", f"calib={calib}")
    db.session.commit()

    return jsonify(code=0, msg=f"转换已启动（PID {proc.pid}）", data={"pid": proc.pid})


# ---------------------------------------------------------------- 8. 模型清单
@train_bp.get("/models")
@login_required
def list_models():
    items = []
    if MODEL_DIR.exists():
        for p in sorted(MODEL_DIR.iterdir()):
            if not p.is_file() or p.name.startswith("."):
                continue
            if p.suffix.lower() not in (".keras", ".tflite", ".json", ".csv", ".png"):
                continue
            items.append({
                "name": p.name,
                "size_kb": round(p.stat().st_size / 1024, 1),
                "mtime": datetime.fromtimestamp(p.stat().st_mtime).strftime(
                    "%Y-%m-%d %H:%M"
                ),
            })

    metrics = None
    if (MODEL_DIR / "metrics.json").exists():
        try:
            metrics = json.loads(
                (MODEL_DIR / "metrics.json").read_text(encoding="utf-8")
            )
        except Exception:
            metrics = None

    # 板端脚本里最后同步过去的模型，方便直接拷卡
    copied = [
        p.name for p in (ROOT / "openmv_script").glob("*.tflite")
    ] if (ROOT / "openmv_script").exists() else []

    return jsonify(
        code=0, msg="ok",
        data={"items": items, "metrics": metrics, "openmv_models": copied},
    )
