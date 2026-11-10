# -*- coding: utf-8 -*-
"""
上传图片的定期清理。

为什么需要：OpenMV 每识别一颗果就传一张图，`uploads/records/` 会一直涨，
硬盘迟早被占满。这里用两个维度控制：

  1. 保留天数：超过 N 天的记录图删除（默认 90 天）
  2. 目录容量：文件数超过 M 张时，从最旧的开始删（默认 2000 张）

删除文件后，会把数据库里指向它的 `sort_record.img_path` 置空 ——
记录本身保留（统计、报表、审计都还在），只是图片腾了空间。
"""

import logging
import os
import threading
import time

from config import Config
from extensions import db
from models import SortRecord

logger = logging.getLogger(__name__)

# 两个阈值都可用 .env 覆盖
RETENTION_DAYS = int(os.getenv("IMAGE_RETENTION_DAYS", "90"))
MAX_FILES = int(os.getenv("IMAGE_MAX_FILES", "2000"))
SUBDIR = "records"


def _iter_record_images():
    """返回 [(mtime, 相对路径)]，相对路径与数据库 img_path 的格式保持一致。"""
    folder = os.path.join(Config.UPLOAD_FOLDER, SUBDIR)
    if not os.path.isdir(folder):
        return []
    items = []
    for name in os.listdir(folder):
        path = os.path.join(folder, name)
        if not os.path.isfile(path):
            continue
        try:
            items.append((os.path.getmtime(path), f"{SUBDIR}/{name}"))
        except OSError as err:
            logger.warning("读取文件信息失败 %s：%s", path, err)
    return items


def cleanup_old_images(retention_days=None, max_files=None):
    """
    执行一次清理，返回统计字典。幂等：重复跑不会出错。
    """
    days = RETENTION_DAYS if retention_days is None else retention_days
    limit = MAX_FILES if max_files is None else max_files

    items = _iter_record_images()
    if not items:
        return {"scanned": 0, "deleted": 0, "cleared_rows": 0}

    deadline = time.time() - max(0, days) * 86400
    to_delete = [rel for (mtime, rel) in items if mtime < deadline]
    deleted_set = set(to_delete)

    # 数量超限：把剩下的按时间从旧到新排，删掉超出上限的最旧部分
    if limit > 0:
        remain = sorted([(mtime, rel) for (mtime, rel) in items if rel not in deleted_set])
        overflow = len(remain) - limit
        if overflow > 0:
            to_delete.extend([rel for (_m, rel) in remain[:overflow]])

    if not to_delete:
        return {"scanned": len(items), "deleted": 0, "cleared_rows": 0}

    folder = os.path.join(Config.UPLOAD_FOLDER, SUBDIR)
    removed = []
    for rel in to_delete:
        full = os.path.join(folder, os.path.basename(rel))
        try:
            os.remove(full)
            removed.append(rel)
        except OSError as err:
            logger.warning("删除图片失败 %s：%s", full, err)

    cleared = 0
    if removed:
        try:
            cleared = (
                db.session.query(SortRecord)
                .filter(SortRecord.img_path.in_(removed))
                .update({SortRecord.img_path: ""}, synchronize_session=False)
            )
            db.session.commit()
        except Exception:
            db.session.rollback()
            logger.exception("清空失效图片路径时出错")

    logger.info(
        "图片清理完成：扫描 %d，删除 %d，清空记录图片字段 %d（保留 %d 天 / 上限 %d 张）",
        len(items), len(removed), cleared, days, limit,
    )
    return {"scanned": len(items), "deleted": len(removed), "cleared_rows": cleared}


def start_cleanup_thread(app, interval_hours=24):
    """后台守护线程：启动时先跑一次，之后每 interval_hours 小时跑一次。"""
    def _loop():
        with app.app_context():
            while True:
                try:
                    cleanup_old_images()
                except Exception:
                    logger.exception("图片清理任务异常")
                time.sleep(max(1, interval_hours) * 3600)

    thread = threading.Thread(target=_loop, name="image-cleanup", daemon=True)
    thread.start()
    logger.info("图片清理线程已启动（每 %s 小时一次）", interval_hours)
