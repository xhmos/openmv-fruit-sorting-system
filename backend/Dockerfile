# 后端 Flask + SocketIO 运行镜像
# 基础镜像：Python 3.12（与本地后端运行环境一致，匹配 numpy/opencv/Deprecated 的 wheel）
FROM python:3.12-slim

# 不生成 pyc 文件、日志不缓冲
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# 把 Debian apt 源切换为清华镜像（trixie），避免国外源下载卡住
RUN set -eux; \
    if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
        sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g; s|security.debian.org|mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list.d/debian.sources; \
    fi; \
    if [ -f /etc/apt/sources.list ]; then \
        sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g; s|security.debian.org|mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list; \
    fi

# 安装系统级依赖：编译部分 pip 包、opencv 运行所需的基础库
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    && rm -rf /var/lib/apt/lists/*

# 工作目录（容器内后端代码目录）
WORKDIR /app/backend

# 先拷依赖清单，利用 Docker 层缓存
COPY requirements.txt ./
# 用国内清华源安装依赖，加快构建
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

# 拷贝后端源码
COPY . ./

# 上传图片目录（容器内，挂载到宿主机持久化）
RUN mkdir -p uploads

# 数据库连接在 docker-compose.yml 的 environment 中注入（避免 Dockerfile ENV 对 $ 做展开）
# DB_USER / DB_PASSWORD / DB_HOST / DB_PORT / DB_NAME 由编排层提供

# 暴露后端端口
EXPOSE 5000

# 生产模式：gunicorn + eventlet worker（eventlet 原生支持 WebSocket/长连接）
# -w 1：SocketIO 有状态推送，单 worker 避免跨进程会话问题；--worker-tmp-dir 避免 /dev/shm 限制
ENV FLASK_DEBUG=0 \
    HOST=0.0.0.0 \
    PORT=5000

CMD ["gunicorn", "-k", "eventlet", "-w", "1", "-b", "0.0.0.0:5000", "--worker-tmp-dir", "/dev/shm", "--timeout", "120", "wsgi:app"]
