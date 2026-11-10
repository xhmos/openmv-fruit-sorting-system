# -*- coding: utf-8 -*-
"""Flask 扩展实例集中定义，避免循环导入。"""

from flask_bcrypt import Bcrypt
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_socketio import SocketIO
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
bcrypt = Bcrypt()
socketio = SocketIO()

# 全局兜底限流：没单独配置的接口 200 次/分钟
limiter = Limiter(key_func=get_remote_address, default_limits=["200 per minute"])
