# -*- coding: utf-8 -*-
"""
生产模式启动脚本（Windows 友好）：waitress + Flask-SocketIO。

与开发模式（app.py）的区别：
  - 关掉 debug / reloader / Werkzeug 调试器
  - 用 waitress 多线程 WSGI 服务器替代 wsgiref 单线程
  - 日志仍然写 backend/logs/app.log（同一套 logging 配置）

重要说明（实测结论）：本机 waitress 3.0.2 + simple-websocket 1.1.0 组合下，
Socket.IO 能正常完成 websocket 升级 —— 客户端 transport 实际为 websocket，
推送实时到达，MJPEG 长连接也正常。不需要额外上 gunicorn / eventlet。
若换到不透传 WSGI socket 的服务器，Socket.IO 会自动退化为长轮询，功能不受影响，只是延迟略高。

用法：
    .\\backend\\venv\\Scripts\\python.exe deploy\\start_waitress.py
"""

import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, "backend"))

# 生产默认关闭 debug；即便忘了设，这里也兜底
os.environ.setdefault("FLASK_DEBUG", "0")

from app import app, socketio  # noqa: E402
from utils.housekeeping import start_cleanup_thread  # noqa: E402
from waitress import serve  # noqa: E402

if __name__ == "__main__":
    # 生产模式下后台清理线程要显式启动（app.py 里只在 __main__ 里起）
    start_cleanup_thread(app)

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "5000"))
    threads = int(os.getenv("THREADS", "8"))

    print(f"[waitress] 监听 http://{host}:{port}，线程数 {threads}，debug 已关闭")
    # 注意：要传 Flask 的 app，不能传 socketio。
    # socketio.init_app(app) 已经把 app.wsgi_app 包上了 Socket.IO 中间件，
    # 传 app 请求才会先经过中间件；直接传 socketio 会报 "'SocketIO' object is not callable"。
    serve(app, host=host, port=port, threads=threads)
