# -*- coding: utf-8 -*-
"""程序入口：创建 Flask 应用 + SocketIO 启动。"""

import logging
import os

from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS

from config import Config
from extensions import bcrypt, db, limiter, socketio

logger = logging.getLogger(__name__)


def _seed_admin(app):
    """首次启动创建默认管理员，已存在就跳过（幂等）。"""
    from models import User

    username = app.config["DEFAULT_ADMIN_USER"]
    if User.query.filter_by(username=username).first():
        return
    user = User(username=username, role="admin", is_active=True)
    user.set_password(app.config["DEFAULT_ADMIN_PASSWORD"])
    db.session.add(user)
    db.session.commit()
    # 不把密码打进日志：日志文件可能被拷走
    logger.info("已创建默认管理员：%s（请尽快修改默认密码）", username)


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # 日志要在最前面初始化，后面所有模块的 logger 都会用这套 handler
    from utils.applog import setup_logging

    setup_logging()

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    db.init_app(app)
    bcrypt.init_app(app)
    limiter.init_app(app)

    # 只放行白名单域名，不使用 *
    # 白名单 = .env 配置 + 本机各网卡地址（见 config.py 的 _build_cors_origins）
    CORS(
        app,
        resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}},
        supports_credentials=True,
    )
    socketio.init_app(app, cors_allowed_origins=app.config["CORS_ORIGINS"])

    # ---------- 蓝图注册 ----------
    from routes.auth import auth_bp
    from routes.device import device_bp
    from routes.record import record_bp
    from routes.setting import setting_bp
    from routes.system import system_bp
    from routes.user import user_bp

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(device_bp, url_prefix="/api/device")
    app.register_blueprint(record_bp, url_prefix="/api/record")
    app.register_blueprint(setting_bp, url_prefix="/api/setting")
    app.register_blueprint(system_bp, url_prefix="/api/system")
    app.register_blueprint(user_bp, url_prefix="/api/user")

    # ---------- 上传图片的访问入口 ----------
    @app.get("/uploads/<path:filename>")
    def uploaded_file(filename):
        # send_from_directory 内部做了路径穿越防护
        return send_from_directory(app.config["UPLOAD_FOLDER"], filename, max_age=60)

    # ---------- 统一错误响应 ----------
    @app.errorhandler(413)
    def too_large(_):
        return jsonify(code=413, msg="上传内容超过大小限制"), 413

    @app.errorhandler(429)
    def too_many(_):
        return jsonify(code=429, msg="请求过于频繁，请稍后再试"), 429

    @app.get("/api/health")
    def health():
        return jsonify(code=0, msg="ok", data={"service": "fruit-sorting-backend"})

    # ---------- SocketIO 连接鉴权 ----------
    # 之前是裸广播：任何人连上 /socket.io/ 就能收到全量分拣数据。
    # 现在握手阶段必须携带有效 JWT（放在 auth 里），否则拒绝连接。
    @socketio.on("connect")
    def _check_socket_auth(auth):
        from models import User
        from utils.security import decode_token

        token = ""
        if isinstance(auth, dict):
            token = (auth.get("token") or "").strip()

        if not token:
            logger.warning("SocketIO 拒绝连接：未携带令牌")
            return False

        try:
            payload = decode_token(token)
        except Exception:
            logger.warning("SocketIO 拒绝连接：令牌无效或已过期")
            return False

        # 和 REST 接口一样，以数据库为准，不信任 token 里的 role
        user = db.session.get(User, payload.get("uid"))
        if user is None or not user.is_active:
            logger.warning("SocketIO 拒绝连接：账号不存在或已被禁用")
            return False

        logger.info("SocketIO 已连接：%s (%s)", user.username, user.role)
        return True

    # ---------- 建表 + 初始数据 ----------
    with app.app_context():
        db.create_all()
        _seed_admin(app)

    logger.info("应用初始化完成，跨域白名单：%s", ", ".join(app.config["CORS_ORIGINS"]))
    return app


app = create_app()


if __name__ == "__main__":
    # 开发环境默认 debug=True；部署时用 FLASK_DEBUG=0 关掉
    debug = os.getenv("FLASK_DEBUG", "1") == "1"

    # Werkzeug 的 reloader 会把本文件跑两遍，只在真正服务的子进程里起清理线程
    if (not debug) or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        from utils.housekeeping import start_cleanup_thread

        start_cleanup_thread(app)

    # allow_unsafe_werkzeug=True 是 Flask-SocketIO 开发模式下用 Werkzeug 的开关
    socketio.run(
        app,
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "5000")),
        debug=debug,
        allow_unsafe_werkzeug=True,
    )
