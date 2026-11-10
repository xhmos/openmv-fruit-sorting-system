# -*- coding: utf-8 -*-
"""安全工具：文本转义、JWT、权限装饰器、上传图片校验。"""

import html
import os
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt
from flask import g, jsonify, request

from config import Config
from extensions import db
from models import User

USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,20}$")

# 图片真实文件头（魔数），用来防“改后缀”绕过
IMAGE_SIGNATURES = (
    (b"\xff\xd8\xff", "jpg"),
    (b"\x89PNG\r\n\x1a\n", "png"),
)


# ---------------------------------------------------------------- 输入过滤
def sanitize_text(value, max_len=50):
    """去首尾空格 + HTML 转义，挡住往用户名里塞 <script> 的 XSS。"""
    if not isinstance(value, str):
        return ""
    return html.escape(value.strip())[:max_len]


def is_valid_username(username: str) -> bool:
    return bool(username) and bool(USERNAME_RE.match(username))


# ---------------------------------------------------------------- JWT
def generate_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "uid": user.id,
        "username": user.username,
        "role": user.role,
        "iat": now,
        "exp": now + timedelta(hours=Config.JWT_EXPIRE_HOURS),
    }
    return jwt.encode(payload, Config.JWT_SECRET, algorithm="HS256")


def decode_token(token: str) -> dict:
    return jwt.decode(token, Config.JWT_SECRET, algorithms=["HS256"])


def _authenticate():
    """解析请求头 token 并查库。成功返回 (user, None)，失败返回 (None, 响应)。"""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None, (jsonify(code=401, msg="未登录或缺少令牌"), 401)
    token = auth[7:].strip()
    if not token:
        return None, (jsonify(code=401, msg="令牌为空"), 401)
    try:
        payload = decode_token(token)
    except jwt.ExpiredSignatureError:
        return None, (jsonify(code=401, msg="登录已过期，请重新登录"), 401)
    except jwt.InvalidTokenError:
        return None, (jsonify(code=401, msg="令牌无效"), 401)

    # 注意：角色以数据库为准，不信任 token 里的 role
    user = db.session.get(User, payload.get("uid"))
    if user is None or not user.is_active:
        return None, (jsonify(code=401, msg="账号不存在或已被禁用"), 401)
    return user, None


def login_required(fn):
    """任意已登录用户（admin / operator）可访问。"""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        user, error = _authenticate()
        if error:
            return error
        g.current_user = user
        return fn(*args, **kwargs)

    return wrapper


def admin_required(fn):
    """仅管理员可访问：后端二次校验，前端隐藏按钮不能当权限。"""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        user, error = _authenticate()
        if error:
            return error
        if user.role != "admin":
            return jsonify(code=403, msg="无权限，仅管理员可操作"), 403
        g.current_user = user
        return fn(*args, **kwargs)

    return wrapper


# ---------------------------------------------------------------- 上传校验
def _sniff_image_type(head: bytes):
    for signature, ext in IMAGE_SIGNATURES:
        if head.startswith(signature):
            return ext
    return None


def save_upload_image(file_storage, sub_dir="records"):
    """
    校验并保存一张图片。
    返回 (True, 相对 uploads 的路径) 或 (False, 错误原因)。
    顺序：有无文件 -> 后缀白名单 -> 体积 -> 真实文件头 -> 重命名落盘。
    """
    if file_storage is None or not file_storage.filename:
        return False, "未接收到图片文件"

    filename = file_storage.filename
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in Config.ALLOWED_EXTENSIONS:
        return False, "只允许上传 jpg / jpeg / png 图片"

    data = file_storage.read()
    file_storage.seek(0)
    if not data:
        return False, "图片内容为空"
    if len(data) > Config.MAX_IMAGE_BYTES:
        return False, "图片超过 2MB 限制"

    real_ext = _sniff_image_type(data[:16])
    if real_ext is None:
        return False, "文件内容不是有效图片（疑似改后缀绕过）"
    if real_ext == "png" and ext != "png":
        return False, "文件后缀与真实格式不一致"
    if real_ext == "jpg" and ext not in ("jpg", "jpeg"):
        return False, "文件后缀与真实格式不一致"

    folder = os.path.join(Config.UPLOAD_FOLDER, sub_dir)
    os.makedirs(folder, exist_ok=True)

    # 用时间戳 + 随机串重命名，丢弃客户端文件名，防 ../ 路径穿越
    safe_name = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:10]}.{real_ext}"
    abs_path = os.path.join(folder, safe_name)
    with open(abs_path, "wb") as f:
        f.write(data)

    return True, f"{sub_dir}/{safe_name}"

# ---------------------------------------------------------------- 设备鉴权
def device_required(fn):
    """OpenMV 用固定设备令牌接入，不参与用户登录体系。"""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        token = request.headers.get("X-Device-Token", "")
        if not token or not secrets.compare_digest(token, Config.DEVICE_TOKEN):
            return jsonify(code=401, msg="设备令牌无效"), 401
        return fn(*args, **kwargs)

    return wrapper


# ---------------------------------------------------------------- 审计日志
def write_operation_log(action, target="", detail=""):
    """
    记录敏感操作。只 add 不 commit，跟随调用方的事务一起提交，
    这样业务失败时不会留下“假日志”。
    """
    from models import OperationLog

    user = getattr(g, "current_user", None)
    log = OperationLog(
        user_id=user.id if user else None,
        username=user.username if user else "system",
        action=str(action)[:100],
        target=str(target)[:100],
        detail=str(detail)[:255],
        ip=(request.headers.get("X-Forwarded-For", request.remote_addr) or "")[:50],
    )
    db.session.add(log)
