# -*- coding: utf-8 -*-
"""
生产模式启动入口：gunicorn + eventlet worker 承载 Flask-SocketIO。

与开发模式（app.py 直接 socketio.run）的区别：
  - 用 gunicorn 多进程/协程对外服务，替代 Werkzeug 内置开发服务器
  - eventlet worker 原生支持 WebSocket 与长连接，SocketIO 实时推送、
    MJPEG 实时流不会退化为轮询
  - 关闭 debug / reloader
  - 后台图片清理线程在这里显式启动

gunicorn 命令行由 Dockerfile / compose 调用：
    gunicorn -k eventlet -w 1 -b 0.0.0.0:5000 --worker-tmp-dir /dev/shm wsgi:app
"""

import os

# 生产环境兜底：关闭 debug
os.environ.setdefault("FLASK_DEBUG", "0")

from app import app, socketio  # noqa: E402
from utils.housekeeping import start_cleanup_thread  # noqa: E402

# 启动图片定期清理守护线程
start_cleanup_thread(app)

# gunicorn 加载的 WSGI 应用对象；SocketIO 中间件已由 socketio.init_app 包在 app.wsgi_app 上
application = app

if __name__ == "__main__":
    # 直接 python wsgi.py 时回退到 SocketIO 自带启动（调试用），正式跑由 gunicorn 接管
    socketio.run(
        app,
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "5000")),
        debug=False,
        allow_unsafe_werkzeug=True,
    )
