# -*- coding: utf-8 -*-
"""
网关层攻击同步：把 Nginx 直接挡掉、根本没进到 Flask 的探测也纳入统计。

为什么需要
    像 GET /_nuxt/../../../../etc/passwd 这种请求，Nginx 在 URI 规范化阶段
    就直接返回 400，请求根本不会转发给后端，应用层中间件看不到它。
    但这恰恰是最典型的「有人在扫我们」——服务器上已经真实发生过。

怎么接
    前端容器把 access log 写到挂载目录 ./logs/nginx/access.log，
    后端容器挂同一目录；这里增量读取新增行，把 400/444 和可疑 404
    记成 gateway_block 事件。

增量读取
    偏移量保存在同目录的 .offset 文件（落盘在宿主机），容器重启不会把
    旧日志重复算一遍；日志被轮转导致 offset 大于文件大小时自动从头读。
"""

import logging
import os
import re
import time

from utils.security_guard import record_event

logger = logging.getLogger(__name__)

LOG_DIR = os.getenv("NGINX_LOG_DIR", "/app/logs/nginx")
LOG_FILE = os.path.join(LOG_DIR, "access.log")
OFFSET_FILE = os.path.join(LOG_DIR, ".offset")

MAX_LINES_PER_SYNC = 500
SYNC_INTERVAL = 60  # 秒，安全总览页每次打开最多同步一次

_LINE_RE = re.compile(
    r'^(?P<ip>\S+) - \[(?P<time>[^\]]*)\] "(?P<req>[^"]*)" (?P<status>\d{3})'
)
_REQ_RE = re.compile(r"^(?P<method>[A-Z]+) (?P<uri>\S*)(?: HTTP/\d\.\d)?$")
_SUSPECT_RE = re.compile(
    r"\.\.|%2e|%252e|/\.env|/\.git|etc/passwd|wp-login|phpmyadmin|/api/v1|/api/apikey",
    re.IGNORECASE,
)

_last_sync = {"at": 0.0}


def _read_offset():
    try:
        with open(OFFSET_FILE, "r", encoding="utf-8") as f:
            return int((f.read() or "0").strip())
    except (OSError, ValueError):
        return 0


def _write_offset(value):
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(OFFSET_FILE, "w", encoding="utf-8") as f:
            f.write(str(value))
    except OSError:
        pass


def sync_gateway_log(force=False):
    """读取 Nginx 新增日志并写事件，返回本次写入的条数。失败一律静默。"""
    now = time.time()
    if not force and now - _last_sync["at"] < SYNC_INTERVAL:
        return 0
    _last_sync["at"] = now

    if not os.path.isfile(LOG_FILE):
        return 0
    try:
        size = os.path.getsize(LOG_FILE)
    except OSError:
        return 0

    offset = _read_offset()
    if offset > size:  # 日志轮转或被清空
        offset = 0

    try:
        with open(LOG_FILE, "rb") as f:
            f.seek(offset)
            chunk = f.read()
            new_offset = f.tell()
    except OSError:
        return 0

    written = 0
    for line in chunk.decode("utf-8", "replace").splitlines()[-MAX_LINES_PER_SYNC:]:
        m = _LINE_RE.match(line)
        if not m:
            continue
        status = int(m.group("status"))
        req = m.group("req")
        rm = _REQ_RE.match(req)
        uri = (rm.group("uri") if rm else req)[:200]
        ip = m.group("ip")[:50]
        method = rm.group("method") if rm else ""

        if status in (400, 444):
            detail = (
                "网关拒绝畸形请求（多为路径穿越探测）"
                if status == 400
                else "网关直接断开连接"
            )
            record_event(
                "gateway_block", detail=detail, status_code=status,
                ip=ip, path=uri, method=method,
            )
            written += 1
        elif status == 404 and _SUSPECT_RE.search(uri):
            record_event(
                "gateway_block", detail="网关层 404：探测不存在的敏感路径",
                status_code=404, ip=ip, path=uri, method=method,
            )
            written += 1

    _write_offset(new_offset)
    if written:
        logger.info("网关日志同步：新增 %d 条攻击记录", written)
    return written
