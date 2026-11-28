# -*- coding: utf-8 -*-
"""
安全审计中间件：把「外面有人在尝试攻击我们」的行为记下来，并做基础加固。

设计原则
    1. 正常业务请求几乎零开销：只做几次正则匹配，没命中就不落库。
    2. 只有「像攻击」的请求才写 security_event 表，所以表不会像访问日志一样暴涨。
    3. 同一来源 + 同一类型 + 同一路径，在合并窗口（默认 60 秒）内只占一条记录，
       count 自增 —— 扫描器一秒几十个请求也不会把数据库写崩，次数仍然准确。
    4. 落库用独立连接（db.engine.begin），不参与业务事务：
       业务 commit 失败时，安全日志不会跟着回滚；反过来也不影响正常返回。
    5. 数据库不可用时有熔断，避免每个恶意请求都卡在连接超时上。

识别范围（都是「请求特征」，不看请求内容本身）
    路径扫描、SQL/命令/XSS 注入特征、路径穿越、扫描工具 UA、
    登录失败、未授权(401)、越权(403)、限流(429)、伪造设备令牌、内网地址探测。

注意：detail 里只记录「哪个参数命中了哪类特征」，不保存原始 payload，
避免把攻击载荷原样存进库、又在前端回显出去。
"""

import logging
import re
import threading
import time
from datetime import datetime

from flask import g, request, has_request_context

from config import Config
from extensions import db
from models import SecurityEvent

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------- 事件类型
# 类型 -> (给前端看的中文名, 默认严重级别)
EVENT_META = {
    "scan": ("漏洞扫描 / 路径探测", "medium"),
    "injection": ("注入攻击尝试", "high"),
    "traversal": ("路径穿越尝试", "high"),
    "brute_force": ("登录暴力破解", "high"),
    "unauthorized": ("未授权访问", "low"),
    "forbidden": ("越权访问", "medium"),
    "rate_limited": ("触发访问频率限制", "medium"),
    "bad_device_token": ("伪造设备令牌", "high"),
    "ssrf": ("内网地址探测", "medium"),
    "scanner_ua": ("扫描工具特征", "medium"),
    "bad_request": ("畸形请求", "low"),
    "gateway_block": ("网关层拦截", "medium"),
}

SEVERITY_ORDER = {"high": 3, "medium": 2, "low": 1}


def event_label(event_type):
    return EVENT_META.get(event_type, ("其它异常", "low"))[0]


def event_severity(event_type):
    return EVENT_META.get(event_type, ("其它异常", "low"))[1]


# ---------------------------------------------------------------- 特征库
# 扫描器最爱试的路径（命中即记 scan）
_SCAN_PATH_RE = re.compile(
    r"(?:^|/)"
    r"(?:\.env|\.git|\.svn|\.hg|\.DS_Store|\.aws|\.ssh|\.htaccess|"
    r"wp-admin|wp-login|wp-content|xmlrpc\.php|phpmyadmin|pma|admin\.php|"
    r"phpinfo|actuator|server-status|server-info|cgi-bin|"
    r"etc/passwd|proc/self|shell\.php|db\.php|config\.json|swagger|"
    r"solr|jenkins|manager/html|HNAP1|boaform|console|jmx|druid|"
    r"backup|dump\.sql|\.sql$|\.bak$|\.zip$|\.tar\.gz$)"
    # 这些是别人在扫「我们没做的接口」，正常业务永远走不到
    r"|/api/(?:v1|v2|apikey|api-key|log|logs|stats|config|admin|debug|env|"
    r"token|keys|backup|export|internal)",
    re.IGNORECASE,
)

# SQL / 命令 / XSS 注入的特征片段
_INJECTION_RE = re.compile(
    r"(?:union[\s/+]+select|information_schema|sleep\s*\(\s*\d|benchmark\s*\(|"
    r"updatexml\s*\(|extractvalue\s*\(|or\s+1\s*=\s*1|'\s*or\s+'|"
    r"<script|onerror\s*=|javascript:|srcdoc\s*=|"
    r"\$\{jndi|%24%7bjndi|"
    r";\s*(?:cat|wget|curl|bash|sh)\s+|`\s*id\s*`|\|\s*cat\s+)",
    re.IGNORECASE,
)

# 路径穿越（明文 / URL 编码 / 二次编码）
_TRAVERSAL_RE = re.compile(
    r"\.\./|\.\.\\|%2e%2e(?:%2f|/|\\)|%252e%252e|\.\.%2f", re.IGNORECASE
)

# 常见自动化扫描/攻击工具 UA
_SCANNER_UA_RE = re.compile(
    r"sqlmap|nikto|nmap|masscan|zgrab|nuclei|dirbuster|gobuster|wpscan|"
    r"acunetix|netsparker|openvas|xsstrike|commix|havij|jbrofuzz|whatweb|"
    r"nessus|qualys|hydra|wfuzz|ffuf|feroxbuster",
    re.IGNORECASE,
)

# 不看 body 的路径（实时帧、Socket.IO 握手，高频且无参数）
_SKIP_PATHS = ("/socket.io/", "/uploads/live/")


# ---------------------------------------------------------------- 基础取值
def client_ip():
    """真实来源 IP。ProxyFix 已把 X-Forwarded-For 还原到 remote_addr。"""
    try:
        return (request.remote_addr or "")[:50]
    except RuntimeError:
        return ""


def _request_texts():
    """
    返回 [(字段名, 待检查文本)]。

    表单里的密码字段只标记字段名，不把值带出去；
    文件上传（multipart）不解析 body，避免在审计里读整张图。
    """
    items = [("URL 路径", request.path or "/")]

    # 用 request.args 取解码后的值：query_string 里是 %20 这种编码，
    # 直接匹配会漏掉 "union%20select" 这类，必须用解析后的文本
    if request.args:
        joined = "&".join(
            f"{key}={request.args.get(key, '')}" for key in list(request.args.keys())[:12]
        )
        items.append(("URL 参数", joined[:1500]))

    ctype = (request.content_type or "").lower()
    if request.method in ("POST", "PUT", "PATCH"):
        if ctype.startswith("application/json"):
            body = request.get_json(silent=True)
            if isinstance(body, dict):
                for key in list(body.keys())[:12]:
                    value = body.get(key)
                    if isinstance(value, str):
                        items.append((f"JSON.{str(key)[:30]}", value[:1500]))
                    elif isinstance(value, (int, float, bool)):
                        items.append((f"JSON.{str(key)[:30]}", str(value)))
        elif ctype.startswith("application/x-www-form-urlencoded"):
            for key in list(request.form.keys())[:12]:
                if key.lower() in ("password", "passwd", "pwd", "token"):
                    continue  # 密码不带走
                items.append((f"表单.{str(key)[:30]}", request.form.get(key, "")[:1500]))

    return items


def _detect_request():
    """检查当前请求，返回 [(事件类型, detail)]，按严重程度从高到低。"""
    hits = []
    seen = set()

    def add(event_type, detail):
        if event_type in seen:
            return
        seen.add(event_type)
        hits.append((event_type, detail))

    # 扫描工具 UA（先判，命中说明后面那些也大概率不是误报）
    ua = request.headers.get("User-Agent", "") or ""
    if _SCANNER_UA_RE.search(ua):
        add("scanner_ua", f"User-Agent 命中扫描工具特征：{ua[:60]}")

    # 路径穿越 > 注入 > 路径扫描
    for source, text in _request_texts():
        if _TRAVERSAL_RE.search(text):
            add("traversal", f"{source} 含 ../ 类穿越片段")
    for source, text in _request_texts():
        if _INJECTION_RE.search(text):
            add("injection", f"{source} 命中 SQL/命令/脚本注入特征")

    if _SCAN_PATH_RE.search(request.path or ""):
        add("scan", f"探测不存在的敏感路径：{(request.path or '')[:100]}")

    return hits


# ---------------------------------------------------------------- 落库
_LOCK = threading.Lock()
_RECENT = {}  # key -> [event_id, last_ts]
_RECENT_MAX = 3000
_FAIL = {"count": 0, "until": 0.0}
_FAIL_THRESHOLD = 3
_FAIL_COOLDOWN = 60.0


def _can_write():
    now = time.time()
    if _FAIL["until"] > now:
        return False
    return True


def _mark_fail():
    _FAIL["count"] += 1
    if _FAIL["count"] >= _FAIL_THRESHOLD:
        _FAIL["until"] = time.time() + _FAIL_COOLDOWN
        _FAIL["count"] = 0
        logger.warning("安全审计落库连续失败，暂停 %.0f 秒", _FAIL_COOLDOWN)


def _mark_ok():
    _FAIL["count"] = 0


def _safe_str(value, limit):
    return (str(value or ""))[:limit]


def record_event(event_type, detail="", severity=None, username="", status_code=None,
                 ip=None, path=None, method=None, user_agent=None):
    """
    记录一次安全事件。任何异常都被吞掉并写日志 —— 审计失败不能影响业务。

    ip / path / method / user_agent 显式传入时优先使用，
    不传则取当前请求的（网关日志同步这类「没有请求上下文」的场景必须显式传）。
    """
    if not _can_write():
        return

    try:
        has_ctx = has_request_context()
        with _LOCK:
            now_ts = time.time()
            ip = _safe_str(ip if ip is not None else (client_ip() if has_ctx else ""), 50)
            path = _safe_str(
                path if path is not None else (request.path if has_ctx else "/"), 255
            )
            method = _safe_str(
                method if method is not None else (request.method if has_ctx else ""), 10
            )
            ua = _safe_str(
                user_agent if user_agent is not None
                else (request.headers.get("User-Agent", "") if has_ctx else ""),
                200,
            )

            key = f"{ip}|{event_type}|{path[:120]}"
            hit = _RECENT.get(key)
            window = max(10, int(Config.SECURITY_MERGE_WINDOW))
            if hit and now_ts - hit[1] < window:
                hit[1] = now_ts
                merged = True
            else:
                merged = False
                if len(_RECENT) > _RECENT_MAX:
                    _RECENT.clear()

        # 合并窗口内：只把已有记录的次数 +1，不新增行
        if merged:
            with db.engine.begin() as conn:
                conn.execute(
                    SecurityEvent.__table__.update()
                    .where(SecurityEvent.__table__.c.id == hit[0])
                    .values(
                        count=SecurityEvent.__table__.c.count + 1,
                        last_time=datetime.now(),
                    )
                )
            _mark_ok()
            return

        payload = {
            "ip": ip,
            "event_type": event_type,
            "severity": severity or event_severity(event_type),
            "method": method,
            "path": path,
            "status_code": int(status_code or 0),
            "username": _safe_str(username, 50),
            "user_agent": ua,
            "detail": _safe_str(detail, 255),
            "count": 1,
            "first_time": datetime.now(),
            "last_time": datetime.now(),
        }
        with db.engine.begin() as conn:
            result = conn.execute(SecurityEvent.__table__.insert().values(**payload))
            new_id = result.inserted_primary_key[0] if result.inserted_primary_key else None

        if new_id:
            with _LOCK:
                _RECENT[key] = [new_id, now_ts]
        _mark_ok()
    except Exception:
        _mark_fail()
        logger.exception("安全事件写入失败：%s", event_type)


# ---------------------------------------------------------------- 中间件
def _before_request():
    g.security_hits = _detect_request()


def _after_request(response):
    _add_security_headers(response)

    try:
        if not _should_audit(response):
            return response

        hits = getattr(g, "security_hits", None) or []
        for event_type, detail in hits:
            record_event(event_type, detail=detail, status_code=response.status_code)

        status = response.status_code
        path = request.path or ""

        if status == 403 and path != "/api/auth/login":
            # 登录接口的 403 是「账号被禁用」，不是越权，不记
            record_event("forbidden", detail="已登录但权限不足", status_code=status)
        elif status == 429:
            record_event("rate_limited", detail="超过限流阈值，请求被拒", status_code=status)
        elif status == 401 and path != "/api/auth/login":
            # 登录失败的 401 由 auth 路由记成「暴力破解」，这里跳过避免重复
            record_event("unauthorized", detail="未携带有效令牌访问接口", status_code=status)
        elif status == 404:
            # 图片被清理后旧链接 404 是正常现象，不看；
            # 其它 404（不存在的接口/路径）基本都是有人在试，记低危
            ua = request.headers.get("User-Agent", "") or ""
            hit_types = {h[0] for h in hits}
            if "scan" in hit_types:
                # 特征库已经判定为扫描，不再重复记一次
                pass
            elif _SCANNER_UA_RE.search(ua):
                record_event("scan", detail="404 + 扫描工具 UA", status_code=404)
            elif not path.startswith("/uploads/"):
                record_event(
                    "scan",
                    detail="访问不存在的接口或路径",
                    status_code=404,
                    severity="low",
                )
    except Exception:
        logger.exception("安全审计 after_request 异常")

    return response


def _should_audit(response):
    if request.method == "OPTIONS":
        return False
    if request.path.startswith(_SKIP_PATHS):
        return False
    return True


def _add_security_headers(response):
    """
    基础加固响应头。都不影响现有功能：
      - nosniff：禁止浏览器猜 MIME（防把上传文件当脚本执行）
      - SAMEORIGIN：禁止被别的站点 iframe 嵌入（防点击劫持）
      - CSP：只允许同源资源，压住 XSS 的影响面
        style 留 unsafe-inline 是因为 Element Plus 运行时注入样式；
        connect 放 ws/wss 是为了 Socket.IO。
    """
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault(
        "Permissions-Policy", "geolocation=(), microphone=(), camera=(self)"
    )
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; "
        "img-src 'self' data: blob:; "
        "media-src 'self' blob:; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "connect-src 'self' ws: wss:; "
        "font-src 'self' data:; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "frame-ancestors 'self'",
    )
    # 有 HTTPS 时才发 HSTS，纯 HTTP 下发了会导致浏览器以后强制跳 https
    if request.is_secure:
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
    return response


def install_security_guard(app):
    """在 create_app 里调用一次即可。"""
    app.before_request(_before_request)
    app.after_request(_after_request)
    logger.info(
        "安全审计已启用（合并窗口 %s 秒）", Config.SECURITY_MERGE_WINDOW
    )
