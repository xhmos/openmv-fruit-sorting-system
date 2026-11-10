# -*- coding: utf-8 -*-
"""全局配置：数据库、密钥、上传限制、跨域白名单。"""

import os
import socket
from urllib.parse import quote_plus

from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))


def _local_frontend_origins(port="5173"):
    """
    把本机各网卡的 IPv4 对应的前端地址加入跨域白名单。

    原因：用局域网 IP（如 http://10.153.180.220:5173）在手机或另一台电脑上打开时，
    浏览器发出的 Origin 就是那个地址，只靠 localhost / 127.0.0.1 会被 CORS 拦住。

    注意安全边界：只加「本机自己的地址 + 固定前端端口」，不是放 *，
    evil.com 之类的第三方来源仍然会被拒绝。
    """
    ips = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    try:
        # 不实际发包，只让系统选出默认出口网卡，拿到它的地址
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect(("8.8.8.8", 80))
        ips.add(probe.getsockname()[0])
        probe.close()
    except OSError:
        pass
    ips.add("127.0.0.1")
    # 169.254.x.x 是链路本地地址，没有实际用途
    return [f"http://{ip}:{port}" for ip in sorted(ips) if not ip.startswith("169.254.")]


def _build_cors_origins():
    origins = [
        o.strip()
        for o in os.getenv(
            "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
        ).split(",")
        if o.strip()
    ]
    for extra in _local_frontend_origins():
        if extra not in origins:
            origins.append(extra)
    return origins


class Config:
    # ---------- 基础 ----------
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
    JWT_SECRET = os.getenv("JWT_SECRET", SECRET_KEY)
    JWT_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "8"))

    # ---------- MySQL ----------
    DB_USER = os.getenv("DB_USER", "root")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
    DB_PORT = os.getenv("DB_PORT", "3306")
    DB_NAME = os.getenv("DB_NAME", "openmv_ai")

    SQLALCHEMY_DATABASE_URI = (
        f"mysql+pymysql://{DB_USER}:{quote_plus(DB_PASSWORD)}"
        f"@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 280,
    }

        # ---------- 设备接入令牌（OpenMV 上报用） ----------
    DEVICE_TOKEN = os.getenv("DEVICE_TOKEN", "openmv-device-2026")


    # ---------- 上传 ----------
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
    ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png"}
    MAX_IMAGE_BYTES = 2 * 1024 * 1024
    MAX_CONTENT_LENGTH = 3 * 1024 * 1024

    # ---------- 跨域白名单 ----------
    # .env 里配置的来源 + 本机各网卡地址对应的前端(5173)，仍然不使用 *
    CORS_ORIGINS = _build_cors_origins()

    # ---------- 首次启动自动创建的管理员 ----------
    DEFAULT_ADMIN_USER = os.getenv("DEFAULT_ADMIN_USER", "admin")
    DEFAULT_ADMIN_PASSWORD = os.getenv("DEFAULT_ADMIN_PASSWORD", "admin123")
