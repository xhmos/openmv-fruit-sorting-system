# -*- coding: utf-8 -*-
"""分拣记录：分页查询、统计、删除、Excel 导出。"""

import os
from datetime import datetime, timedelta
from io import BytesIO

from flask import Blueprint, jsonify, request, send_file
from sqlalchemy import case, func

from config import Config
from extensions import db
from models import SortRecord
from utils.export_excel import build_records_workbook
from utils.security import admin_required, login_required, write_operation_log

record_bp = Blueprint("record", __name__)

MAX_EXPORT_ROWS = 50000


def _parse_dt(value, is_end=False):
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(value, fmt)
            if is_end and fmt == "%Y-%m-%d":
                dt = dt.replace(hour=23, minute=59, second=59)
            return dt
        except ValueError:
            continue
    return None


def _apply_filters(stmt, args):
    """把查询参数应用到 select，列表和导出共用同一套筛选逻辑。"""
    fruit_type = (args.get("fruit_type") or "").strip()
    result = (args.get("result") or "").strip().lower()
    start = _parse_dt(args.get("start"))
    end = _parse_dt(args.get("end"), is_end=True)

    if fruit_type:
        stmt = stmt.where(SortRecord.fruit_type == fruit_type)
    if result in ("good", "bad"):
        stmt = stmt.where(SortRecord.result == result)
    if start:
        stmt = stmt.where(SortRecord.create_time >= start)
    if end:
        stmt = stmt.where(SortRecord.create_time <= end)
    return stmt


def _with_img_url(record):
    data = record.to_dict()
    data["img_url"] = f"/uploads/{record.img_path}" if record.img_path else ""
    return data


def _remove_image(rel_path):
    """删除记录时顺手清掉图片，避免 uploads 越积越大。"""
    if not rel_path:
        return
    abs_path = os.path.normpath(os.path.join(Config.UPLOAD_FOLDER, rel_path))
    upload_root = os.path.normpath(Config.UPLOAD_FOLDER)
    if abs_path.startswith(upload_root + os.sep) and os.path.isfile(abs_path):
        try:
            os.remove(abs_path)
        except OSError:
            pass


@record_bp.get("/list")
@login_required
def list_records():
    try:
        page = max(1, int(request.args.get("page", 1)))
        page_size = min(100, max(1, int(request.args.get("page_size", 10))))
    except (TypeError, ValueError):
        return jsonify(code=400, msg="分页参数不合法"), 400

    stmt = _apply_filters(db.select(SortRecord), request.args)
    stmt = stmt.order_by(SortRecord.create_time.desc(), SortRecord.id.desc())

    page_obj = db.paginate(stmt, page=page, per_page=page_size, error_out=False)

    return jsonify(
        code=0,
        msg="ok",
        data={
            "items": [_with_img_url(r) for r in page_obj.items],
            "total": page_obj.total,
            "page": page,
            "page_size": page_size,
            "pages": page_obj.pages,
        },
    )


@record_bp.get("/stats")
@login_required
def stats():
    """今日汇总 + 趋势曲线。days=1 按小时，days=7/30 按天。"""
    try:
        days = int(request.args.get("days", 1))
    except (TypeError, ValueError):
        days = 1
    if days not in (1, 7, 30):
        days = 1

    now = datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    today_total = (
        db.session.query(func.count(SortRecord.id))
        .filter(SortRecord.create_time >= today_start)
        .scalar()
        or 0
    )
    today_good = (
        db.session.query(func.count(SortRecord.id))
        .filter(SortRecord.create_time >= today_start, SortRecord.result == "good")
        .scalar()
        or 0
    )
    today_bad = today_total - today_good
    good_rate = round(today_good / today_total * 100, 1) if today_total else 0.0

    # ---------- 趋势桶 ----------
    if days == 1:
        start = (now - timedelta(hours=23)).replace(minute=0, second=0, microsecond=0)
        points = [start + timedelta(hours=i) for i in range(24)]
        sql_fmt, label_fmt = "%Y-%m-%d %H", "%H:00"
    else:
        start = (now - timedelta(days=days - 1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        points = [start + timedelta(days=i) for i in range(days)]
        sql_fmt, label_fmt = "%Y-%m-%d", "%m-%d"

    bucket_expr = func.date_format(SortRecord.create_time, sql_fmt).label("bucket")
    rows = (
        db.session.query(
            bucket_expr,
            func.count(SortRecord.id),
            func.sum(case((SortRecord.result == "good", 1), else_=0)),
        )
        .filter(SortRecord.create_time >= start)
        .group_by(bucket_expr)
        .all()
    )
    bucket_map = {row[0]: (int(row[1]), int(row[2] or 0)) for row in rows}

    labels, totals, goods, rates = [], [], [], []
    for point in points:
        key = point.strftime(sql_fmt)
        total, good = bucket_map.get(key, (0, 0))
        labels.append(point.strftime(label_fmt))
        totals.append(total)
        goods.append(good)
        rates.append(round(good / total * 100, 1) if total else 0.0)

    # ---------- 品种分布 ----------
    by_type = (
        db.session.query(SortRecord.fruit_type, func.count(SortRecord.id))
        .filter(SortRecord.create_time >= today_start)
        .group_by(SortRecord.fruit_type)
        .order_by(func.count(SortRecord.id).desc())
        .limit(8)
        .all()
    )

    return jsonify(
        code=0,
        msg="ok",
        data={
            "summary": {
                "today_total": today_total,
                "today_good": today_good,
                "today_bad": today_bad,
                "good_rate": good_rate,
            },
            "trend": {
                "labels": labels,
                "total": totals,
                "good": goods,
                "rate": rates,
            },
            "by_type": [{"name": row[0], "count": int(row[1])} for row in by_type],
        },
    )


@record_bp.delete("/<int:record_id>")
@admin_required
def delete_record(record_id):
    record = db.session.get(SortRecord, record_id)
    if record is None:
        return jsonify(code=404, msg="记录不存在"), 404

    img_path = record.img_path
    db.session.delete(record)
    write_operation_log("删除分拣记录", f"record#{record_id}", f"品种={record.fruit_type}")
    db.session.commit()
    _remove_image(img_path)

    return jsonify(code=0, msg="已删除")


@record_bp.post("/batch-delete")
@admin_required
def batch_delete():
    ids = (request.get_json(silent=True) or {}).get("ids") or []
    if not isinstance(ids, list) or not ids:
        return jsonify(code=400, msg="ids 不能为空"), 400
    if len(ids) > 100:
        return jsonify(code=400, msg="单次最多删除 100 条"), 400

    try:
        ids = [int(i) for i in ids]
    except (TypeError, ValueError):
        return jsonify(code=400, msg="ids 必须是整数"), 400

    records = db.session.query(SortRecord).filter(SortRecord.id.in_(ids)).all()
    img_paths = [r.img_path for r in records]
    for record in records:
        db.session.delete(record)

    write_operation_log("批量删除分拣记录", f"count={len(records)}", f"ids={ids[:20]}")
    db.session.commit()
    for path in img_paths:
        _remove_image(path)

    return jsonify(code=0, msg=f"已删除 {len(records)} 条", data={"deleted": len(records)})


@record_bp.get("/export")
@admin_required
def export_records():
    """管理员导出全部报表，筛选条件和列表页一致。"""
    stmt = _apply_filters(db.select(SortRecord), request.args)
    stmt = stmt.order_by(SortRecord.create_time.desc()).limit(MAX_EXPORT_ROWS)
    records = db.session.execute(stmt).scalars().all()

    wb = build_records_workbook(records)
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)

    write_operation_log("导出分拣报表", f"count={len(records)}", "xlsx")
    db.session.commit()

    filename = f"sort_record_{datetime.now():%Y%m%d%H%M%S}.xlsx"
    return send_file(
        buf,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
