# -*- coding: utf-8 -*-
"""认证接口：登录 / 当前用户 / 头像 / 退出。"""

import os

from flask import Blueprint, g, jsonify, request

from config import Config
from extensions import db, limiter
from models import User
from utils.security import (
    generate_token,
    is_valid_username,
    login_required,
    sanitize_text,
    save_upload_image,
)

auth_bp = Blueprint("auth", __name__)


@auth_bp.post("/login")
@limiter.limit("5 per minute")  # 防暴力破解：同一 IP 每分钟最多 5 次
def login():
    payload = request.get_json(silent=True) or {}
    username = sanitize_text(payload.get("username"), 50)
    password = payload.get("password")

    if not is_valid_username(username) or not isinstance(password, str):
        return jsonify(code=400, msg="账号或密码格式不正确"), 400
    if not (6 <= len(password) <= 64):
        return jsonify(code=400, msg="账号或密码格式不正确"), 400

    user = User.query.filter_by(username=username).first()
    # 不区分“用户不存在”和“密码错误”，避免枚举账号
    if user is None or not user.check_password(password):
        return jsonify(code=401, msg="账号或密码错误"), 401
    if not user.is_active:
        return jsonify(code=403, msg="该账号已被禁用，请联系管理员"), 403

    return jsonify(
        code=0,
        msg="登录成功",
        data={"token": generate_token(user), "user": user.to_dict()},
    )


@auth_bp.get("/me")
@login_required
def me():
    return jsonify(code=0, msg="ok", data=g.current_user.to_dict())


@auth_bp.post("/logout")
@login_required
def logout():
    # JWT 无状态，前端删本地 token 即可；保留接口方便以后加黑名单
    return jsonify(code=0, msg="已退出登录")


def _remove_avatar_file(rel_path):
    """删掉旧头像文件。失败不影响接口返回，最多留个孤儿文件。"""
    if not rel_path:
        return
    try:
        abs_path = os.path.join(Config.UPLOAD_FOLDER, rel_path)
        if os.path.isfile(abs_path):
            os.remove(abs_path)
    except OSError:
        pass


@auth_bp.post("/avatar")
@login_required
def upload_avatar():
    """上传/更换当前用户头像。表单字段名 file，只收 jpg / png，2MB 以内。"""
    file = request.files.get("file")
    ok, result = save_upload_image(file, "avatars")
    if not ok:
        return jsonify(code=400, msg=result), 400

    user = g.current_user
    old = user.avatar
    user.avatar = result
    db.session.commit()

    # 换新图后删旧图，避免 uploads/avatars 一直涨
    _remove_avatar_file(old)

    return jsonify(code=0, msg="头像已更新", data=user.to_dict())


@auth_bp.delete("/avatar")
@login_required
def reset_avatar():
    """移除头像，界面回到「首字母」占位。"""
    user = g.current_user
    old = user.avatar
    user.avatar = None
    db.session.commit()
    _remove_avatar_file(old)
    return jsonify(code=0, msg="头像已移除", data=user.to_dict())
