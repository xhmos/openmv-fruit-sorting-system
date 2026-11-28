# -*- coding: utf-8 -*-
"""
安全中心接口：给管理员看的「别人怎么攻击我们、试了多少次、有没有得手」。

数据来源是 security_event 表（由 utils/security_guard.py 在请求链路上自动写入），
这里只做聚合查询，不再做检测。

为什么只给管理员：
    攻击来源 IP、试过哪些路径，本身就是侦察情报，
    操作员账号只需要看生产数据，不该看到这些。
"""

from datetime import datetime, timedelta

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy import case, func

from config import Config
from extensions import db
from models import SecurityEvent, User
from utils.security import admin_required, write_operation_log
from utils.security_guard import EVENT_META, event_label, event_severity

security_bp = Blueprint("security", __name__)

MAX_PAGE_SIZE = 100
TREND_DAYS = (1, 7, 30, 90)


# ---------------------------------------------------------------- 小工具
def _days():
    try:
        days = int(request.args.get("days", 7))
    except (TypeError, ValueError):
        days = 7
    if days not in TREND_DAYS:
        days = 7
    return days


def _start_of(days):
    """days=1 取最近 24 小时，其余从 (days-1) 天前的 0 点起算。"""
    now = datetime.now()
    if days == 1:
        return now - timedelta(hours=23)
    return (now - timedelta(days=days - 1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )


def _sum_count(stmt_filter):
    value = (
        db.session.query(func.coalesce(func.sum(SecurityEvent.count), 0))
        .filter(*stmt_filter)
        .scalar()
    )
    # MySQL 的 SUM 会返回 Decimal，统一转 int，前端才能直接相加
    return int(value or 0)


def _event_dict(row):
    data = row.to_dict()
    data["type_label"] = event_label(data["event_type"])
    return data


# ---------------------------------------------------------------- 1. 总览
@security_bp.get("/overview")
@admin_required
def overview():
    # 先把 Nginx 挡掉、没进到应用层的那批探测同步进来（内部有 60 秒节流）
    try:
        from utils.gateway_log import sync_gateway_log

        sync_gateway_log(force=True)
    except Exception:
        pass

    days = _days()
    now = datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start = _start_of(days)

    today_total = _sum_count([SecurityEvent.last_time >= today_start])
    today_events = (
        db.session.query(func.count(SecurityEvent.id))
        .filter(SecurityEvent.last_time >= today_start)
        .scalar()
        or 0
    )
    today_high = _sum_count(
        [SecurityEvent.last_time >= today_start, SecurityEvent.severity == "high"]
    )
    today_ips = (
        db.session.query(func.count(func.distinct(SecurityEvent.ip)))
        .filter(SecurityEvent.last_time >= today_start)
        .scalar()
        or 0
    )

    period_total = _sum_count([SecurityEvent.last_time >= start])
    period_high = _sum_count(
        [SecurityEvent.last_time >= start, SecurityEvent.severity == "high"]
    )
    period_ips = (
        db.session.query(func.count(func.distinct(SecurityEvent.ip)))
        .filter(SecurityEvent.last_time >= start)
        .scalar()
        or 0
    )

    # 被挡住的次数：401/403/429 说明对方「没得手」
    blocked = _sum_count(
        [
            SecurityEvent.last_time >= start,
            SecurityEvent.status_code.in_((401, 403, 429)),
        ]
    )
    gateway_blocked = _sum_count(
        [
            SecurityEvent.last_time >= today_start,
            SecurityEvent.event_type == "gateway_block",
        ]
    )

    # ---------- 趋势 ----------
    if days == 1:
        base = (now - timedelta(hours=23)).replace(minute=0, second=0, microsecond=0)
        points = [base + timedelta(hours=i) for i in range(24)]
        sql_fmt, label_fmt = "%Y-%m-%d %H", "%H:00"
    else:
        points = [_start_of(days) + timedelta(days=i) for i in range(days)]
        sql_fmt, label_fmt = "%Y-%m-%d", "%m-%d"

    bucket = func.date_format(SecurityEvent.last_time, sql_fmt).label("bucket")
    rows = (
        db.session.query(
            bucket,
            func.coalesce(func.sum(SecurityEvent.count), 0),
            func.coalesce(
                func.sum(case((SecurityEvent.severity == "high", SecurityEvent.count), else_=0)), 0
            ),
        )
        .filter(SecurityEvent.last_time >= points[0])
        .group_by(bucket)
        .all()
    )
    bucket_map = {row[0]: (int(row[1] or 0), int(row[2] or 0)) for row in rows}

    labels, totals, highs = [], [], []
    for point in points:
        total, high = bucket_map.get(point.strftime(sql_fmt), (0, 0))
        labels.append(point.strftime(label_fmt))
        totals.append(total)
        highs.append(high)

    # ---------- 攻击方式分布 ----------
    type_rows = (
        db.session.query(
            SecurityEvent.event_type,
            func.coalesce(func.sum(SecurityEvent.count), 0),
        )
        .filter(SecurityEvent.last_time >= start)
        .group_by(SecurityEvent.event_type)
        .all()
    )
    types = [
        {
            "type": row[0],
            "label": event_label(row[0]),
            "severity": event_severity(row[0]),
            "count": int(row[1] or 0),
        }
        for row in type_rows
    ]
    types.sort(key=lambda x: x["count"], reverse=True)

    # ---------- 来源 IP Top ----------
    ip_rows = (
        db.session.query(
            SecurityEvent.ip,
            func.coalesce(func.sum(SecurityEvent.count), 0),
            func.max(SecurityEvent.last_time),
            func.count(SecurityEvent.id),
        )
        .filter(SecurityEvent.last_time >= start)
        .group_by(SecurityEvent.ip)
        .order_by(func.coalesce(func.sum(SecurityEvent.count), 0).desc())
        .limit(8)
        .all()
    )

    top_ips = []
    for row in ip_rows:
        ip = row[0] or "未知"
        type_list = (
            db.session.query(SecurityEvent.event_type)
            .filter(SecurityEvent.ip == row[0], SecurityEvent.last_time >= start)
            .distinct()
            .all()
        )
        top_ips.append({
            "ip": ip,
            "count": int(row[1] or 0),
            "events": int(row[3] or 0),
            "last_time": row[2].strftime("%Y-%m-%d %H:%M:%S") if row[2] else "",
            "types": [event_label(t[0]) for t in type_list][:6],
        })

    # ---------- 最近明细 ----------
    recent = (
        db.session.query(SecurityEvent)
        .order_by(SecurityEvent.last_time.desc())
        .limit(10)
        .all()
    )

    return jsonify(
        code=0,
        msg="ok",
        data={
            "days": days,
            "summary": {
                "today_total": today_total,
                "today_events": today_events,
                "today_high": today_high,
                "today_ips": today_ips,
                "period_total": period_total,
                "period_high": period_high,
                "period_ips": period_ips,
                "blocked": blocked,
                "gateway_blocked": gateway_blocked,
            },
            "trend": {"labels": labels, "total": totals, "high": highs},
            "types": types,
            "top_ips": top_ips,
            "recent": [_event_dict(r) for r in recent],
        },
    )


# ---------------------------------------------------------------- 2. 明细列表
@security_bp.get("/events")
@admin_required
def list_events():
    try:
        page = max(1, int(request.args.get("page", 1)))
        page_size = min(MAX_PAGE_SIZE, max(1, int(request.args.get("page_size", 20))))
    except (TypeError, ValueError):
        return jsonify(code=400, msg="分页参数不合法"), 400

    days = _days()
    start = _start_of(days)

    stmt = db.select(SecurityEvent).where(SecurityEvent.last_time >= start)

    event_type = (request.args.get("type") or "").strip()
    if event_type and event_type in EVENT_META:
        stmt = stmt.where(SecurityEvent.event_type == event_type)

    severity = (request.args.get("severity") or "").strip()
    if severity in ("high", "medium", "low"):
        stmt = stmt.where(SecurityEvent.severity == severity)

    ip = (request.args.get("ip") or "").strip()[:50]
    if ip:
        stmt = stmt.where(SecurityEvent.ip == ip)

    keyword = (request.args.get("keyword") or "").strip()[:50]
    if keyword:
        stmt = stmt.where(SecurityEvent.path.like(f"%{keyword}%"))

    stmt = stmt.order_by(SecurityEvent.last_time.desc(), SecurityEvent.id.desc())
    page_obj = db.paginate(stmt, page=page, per_page=page_size, error_out=False)

    return jsonify(
        code=0,
        msg="ok",
        data={
            "items": [_event_dict(r) for r in page_obj.items],
            "total": page_obj.total,
            "page": page,
            "page_size": page_size,
            "pages": page_obj.pages,
            "types": [
                {"type": key, "label": meta[0], "severity": meta[1]}
                for key, meta in EVENT_META.items()
            ],
        },
    )


# ---------------------------------------------------------------- 3. 安全体检
@security_bp.get("/checklist")
@admin_required
def checklist():
    """
    配置层面的「体检」：不扫端口、不打接口，只读当前配置判断。
    每项返回 ok(Ture/False) 或 None（需要人工确认）。
    """
    app = current_app

    def debug_off():
        flag = str(app.config.get("DEBUG", False)).lower() in ("1", "true", "yes")
        return not flag, "调试模式关闭" if not flag else "调试模式开启，会暴露源码与执行能力"

    def jwt_secret():
        secret = Config.JWT_SECRET or ""
        same = secret == Config.SECRET_KEY
        ok = len(secret) >= 32 and not same
        tip = "长度 ≥32 且与 SECRET_KEY 不同" if ok else (
            "JWT_SECRET 过短或与 SECRET_KEY 相同，令牌可被伪造" if not ok else ""
        )
        return ok, tip

    def secret_key():
        weak = Config.SECRET_KEY in ("dev-secret-key", "", None)
        return (not weak), ("使用默认/空密钥" if weak else "已使用自定义密钥")

    def device_token():
        weak = Config.DEVICE_TOKEN in ("openmv-device-2026", "", None)
        return (not weak), (
            "设备令牌仍是示例值，任何人都能伪造设备上报" if weak else "已使用自定义设备令牌"
        )

    def cors():
        bad = "*" in Config.CORS_ORIGINS
        return (not bad), ("跨域白名单包含 *" if bad else f"白名单 {len(Config.CORS_ORIGINS)} 个来源")

    def https():
        ok = bool(request.is_secure)
        return ok, ("当前请求走 HTTPS" if ok else "当前请求是 HTTP，令牌与图片在网络上明文传输")

    def uploads_open():
        # /uploads/live/latest.jpg 目前不校验登录，属于已知开放面
        return False, "上传目录可被未登录用户直接访问（实时帧 latest.jpg 等）"

    def admin_password():
        # 首启密码写在配置里，改没改只有管理员自己知道
        try:
            names = [u.username for u in User.query.filter_by(role="admin").limit(3).all()]
        except Exception:
            names = []
        who = "、".join(names) if names else "（未读到管理员账号）"
        return None, f"管理员 {who} 的密码请人工确认已修改，首启密码写在部署的 .env 里"

    def rate_limit():
        return True, "登录接口 10 次/分钟，其余接口 200 次/分钟"

    def headers():
        return True, "已下发 CSP / nosniff / X-Frame-Options / Referrer-Policy"

    def event_keep():
        return True, f"安全事件保留 {Config.SECURITY_EVENT_KEEP_DAYS} 天，超出自动清理"

    checks = [
        ("debug", "调试模式", debug_off(), "high"),
        ("jwt", "JWT 密钥强度", jwt_secret(), "high"),
        ("secret", "应用密钥", secret_key(), "high"),
        ("device", "设备上报令牌", device_token(), "high"),
        ("cors", "跨域白名单", cors(), "medium"),
        ("https", "传输加密", https(), "high"),
        ("uploads", "上传目录访问控制", uploads_open(), "medium"),
        ("admin_pwd", "管理员密码", admin_password(), "high"),
        ("rate", "登录限流", rate_limit(), "medium"),
        ("headers", "安全响应头", headers(), "low"),
        ("keep", "安全事件留存", event_keep(), "low"),
    ]

    items = [
        {
            "key": key,
            "name": name,
            "ok": ok,
            "level": level,
            "detail": detail,
        }
        for key, name, (ok, detail), level in checks
    ]
    failed = len([i for i in items if i["ok"] is False])
    unknown = len([i for i in items if i["ok"] is None])

    return jsonify(code=0, msg="ok", data={"items": items, "failed": failed, "unknown": unknown})


# ---------------------------------------------------------------- 4. 清理
@security_bp.delete("/events")
@admin_required
def purge_events():
    """手动清理安全事件，默认删 90 天前的。"""
    try:
        days = int(request.args.get("days", Config.SECURITY_EVENT_KEEP_DAYS))
    except (TypeError, ValueError):
        return jsonify(code=400, msg="days 必须是整数"), 400
    days = max(1, min(365, days))

    deadline = datetime.now() - timedelta(days=days)
    deleted = (
        db.session.query(SecurityEvent)
        .filter(SecurityEvent.last_time < deadline)
        .delete(synchronize_session=False)
    )
    write_operation_log("清理安全事件", f"before={deadline:%Y-%m-%d}", f"删 {deleted} 条")
    db.session.commit()

    return jsonify(code=0, msg=f"已清理 {deleted} 条", data={"deleted": deleted})
