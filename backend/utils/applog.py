# -*- coding: utf-8 -*-
"""
日志落地。

原来只有 print，服务在后台跑时什么都看不到，出了问题只能靠复现。
这里改成标准 logging：同时输出到控制台和 backend/logs/app.log，
按天轮转，保留 14 天，Werkzeug 的访问日志也一并写进去。
"""

import logging
import os
from logging.handlers import TimedRotatingFileHandler

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(log_dir=None, level=logging.INFO, backup_days=14):
    """初始化根 logger，返回日志文件路径。重复调用是安全的（会先清掉旧 handler）。"""
    from config import BASE_DIR

    target = log_dir or os.path.join(BASE_DIR, "logs")
    os.makedirs(target, exist_ok=True)
    log_file = os.path.join(target, "app.log")

    formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)

    file_handler = TimedRotatingFileHandler(
        log_file, when="midnight", backupCount=backup_days, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)

    root = logging.getLogger()
    root.setLevel(level)
    for old in list(root.handlers):
        root.removeHandler(old)
    root.addHandler(file_handler)
    root.addHandler(console_handler)

    # 让 Flask / Werkzeug 的请求日志也进同一个文件（"GET /api/... 200" 那些）
    logging.getLogger("werkzeug").setLevel(level)

    return log_file
