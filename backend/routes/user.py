# -*- coding: utf-8 -*-
"""用户管理：仅管理员可用。"""

from flask import Blueprint, g, jsonify, request

from extensions import db
from models import User
from utils.security import (
    admin_required,
    is_valid_username,
    sanitize_text,
    write_operation_log,
)

user_bp = Blueprint("user", __name__)
ROLE_WHITELIST = {"admin", "operator"}


def _active_admin_count():
    return (
        db.session.query(User)
        .filter(User.role == "admin", User.is_active.is_(True))
        .count()
    )


@user_bp.get("/list")
@admin_required
def list_users():
    try:
        page = max(1, int(request.args.get("page", 1)))
        page_size = min(100, max(1, int(request.args.get("page_size", 10))))
    except (TypeError, ValueError):
        return jsonify(code=400, msg="分页参数不合法"), 400

    keyword = sanitize_text(request.args.get("keyword"), 50)
    stmt = db.select(User)
    if keyword:
        stmt = stmt.where(User.username.like(f"%{keyword}%"))
    stmt = stmt.order_by(User.id.asc())

    page_obj = db.paginate(stmt, page=page, per_page=page_size, error_out=False)
    return jsonify(
        code=0,
        msg="ok",
        data={
            "items": [u.to_dict() for u in page_obj.items],
            "total": page_obj.total,
            "page": page,
            "page_size": page_size,
            "pages": page_obj.pages,
        },
    )


@user_bp.post("/create")
@admin_required
def create_user():
    payload = request.get_json(silent=True) or {}
    username = sanitize_text(payload.get("username"), 50)
    password = payload.get("password")
    role = (payload.get("role") or "operator").strip()

    if not is_valid_username(username):
        return jsonify(code=400, msg="用户名只能是 3~20 位字母、数字或下划线"), 400
    if not isinstance(password, str) or not (6 <= len(password) <= 64):
        return jsonify(code=400, msg="密码长度需在 6~64 位之间"), 400
    if role not in ROLE_WHITELIST:
        return jsonify(code=400, msg="角色只能是 admin / operator"), 400
    if db.session.query(User).filter_by(username=username).first():
        return jsonify(code=409, msg="用户名已存在"), 409

    user = User(username=username, role=role, is_active=True)
    user.set_password(password)
    db.session.add(user)
    write_operation_log("新增用户", username, f"role={role}")
    db.session.commit()

    return jsonify(code=0, msg="已创建", data=user.to_dict()), 201


@user_bp.put("/<int:user_id>/status")
@admin_required
def update_status(user_id):
    target = db.session.get(User, user_id)
    if target is None:
        return jsonify(code=404, msg="用户不存在"), 404

    is_active = (request.get_json(silent=True) or {}).get("is_active")
    if not isinstance(is_active, bool):
        return jsonify(code=400, msg="is_active 必须是 true / false"), 400

    if not is_active and target.id == g.current_user.id:
        return jsonify(code=400, msg="不能禁用当前登录的自己"), 400
    if not is_active and target.role == "admin" and _active_admin_count() <= 1:
        return jsonify(code=400, msg="至少保留一个可用的管理员"), 400

    target.is_active = is_active
    write_operation_log(
        "启用用户" if is_active else "禁用用户", target.username, f"id={target.id}"
    )
    db.session.commit()

    return jsonify(code=0, msg="已更新", data=target.to_dict())


@user_bp.put("/<int:user_id>/password")
@admin_required
def reset_password(user_id):
    target = db.session.get(User, user_id)
    if target is None:
        return jsonify(code=404, msg="用户不存在"), 404

    password = (request.get_json(silent=True) or {}).get("password")
    if not isinstance(password, str) or not (6 <= len(password) <= 64):
        return jsonify(code=400, msg="密码长度需在 6~64 位之间"), 400

    target.set_password(password)
    write_operation_log("重置密码", target.username, f"id={target.id}")
    db.session.commit()

    return jsonify(code=0, msg="密码已重置")


@user_bp.put("/<int:user_id>/role")
@admin_required
def update_role(user_id):
    target = db.session.get(User, user_id)
    if target is None:
        return jsonify(code=404, msg="用户不存在"), 404

    role = ((request.get_json(silent=True) or {}).get("role") or "").strip()
    if role not in ROLE_WHITELIST:
        return jsonify(code=400, msg="角色只能是 admin / operator"), 400

    if role != "admin" and target.role == "admin" and _active_admin_count() <= 1:
        return jsonify(code=400, msg="至少保留一个可用的管理员"), 400

    old_role = target.role
    target.role = role
    write_operation_log("修改角色", target.username, f"{old_role} -> {role}")
    db.session.commit()

    return jsonify(code=0, msg="已更新", data=target.to_dict())


@user_bp.delete("/<int:user_id>")
@admin_required
def delete_user(user_id):
    target = db.session.get(User, user_id)
    if target is None:
        return jsonify(code=404, msg="用户不存在"), 404
    if target.id == g.current_user.id:
        return jsonify(code=400, msg="不能删除当前登录的自己"), 400
    if target.role == "admin" and _active_admin_count() <= 1:
        return jsonify(code=400, msg="至少保留一个可用的管理员"), 400

    username = target.username
    db.session.delete(target)
    write_operation_log("删除用户", username, f"id={user_id}")
    db.session.commit()

    return jsonify(code=0, msg="已删除")
