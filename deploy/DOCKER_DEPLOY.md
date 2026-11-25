# Docker 部署指南（腾讯云 Ubuntu 轻量服务器）

本目录下的 Docker 配置用于把「后端 Flask + 前端 Nginx」打包成容器运行，MySQL 使用服务器本机已安装的数据库。

## 一、部署前确认

- 服务器系统：Ubuntu，已装好 Docker、Docker Compose 插件。
- 服务器 MySQL 已启动，且已建好业务库和业务用户。
- 防火墙已放行 **4173**（网站入口）；**3306 不要对外开放**。

## 二、数据库对齐（在服务器 MySQL 里执行一次）

先确认库名和账号。下面示例库名用 `openmv_ai`，业务用户 `fruit_user`：

```bash
sudo mysql
```

```sql
-- 建库（若已存在可跳过）
CREATE DATABASE IF NOT EXISTS openmv_ai DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- 给业务用户授权（fruit_user 为已有用户）
GRANT ALL PRIVILEGES ON openmv_ai.* TO 'fruit_user'@'localhost';
FLUSH PRIVILEGES;
EXIT;
```

> 注意：MySQL 默认只监听 127.0.0.1。后端容器通过 `host.docker.internal` 访问宿主机 MySQL，需要让 MySQL 允许宿主机网卡来源连接；
> 若容器连不上库，再检查 `/etc/mysql/mysql.conf.d/mysqld.cnf` 里的 `bind-address`，必要时改为 `0.0.0.0`，并确认 `fruit_user` 的 host 允许宿主机内网地址。

## 三、上传项目到服务器

把本地项目上传到服务器 `~/openMV`，**排除以下目录**（体积大且不需要进包）：

- `backend/venv/`
- `frontend/node_modules/`
- `frontend/dist/`
- `train_env/`
- `dataset/`、`models/`（训练产物，按需）
- `backend/logs/`、`backend/uploads/`（运行时数据）
- `.pytest_cache/`

可在本地先打包关键目录：`backend`、`frontend`、`docker-compose.yml`、`train`、`openmv_script`。

## 四、配置环境变量

在服务器项目根目录 `~/openMV`，复制环境变量文件并填写真实数据库信息：

```bash
cp .env.docker .env
nano .env
```

```env
DB_USER=fruit_user
DB_PASSWORD=你的fruit_user密码
DB_NAME=openmv_ai
```

后端 `backend/.env` 里的 `SECRET_KEY`、`JWT_SECRET`、管理员账号等也会随代码带上；容器启动时数据库相关项由 compose 环境变量覆盖。

## 五、构建并启动容器

在服务器项目根目录 `~/openMV` 执行：

```bash
# 构建镜像并后台启动
sudo docker compose up -d --build
```

查看运行状态：

```bash
sudo docker compose ps
```

查看后端日志（排查报错）：

```bash
sudo docker compose logs -f backend
```

查看前端日志：

```bash
sudo docker compose logs -f frontend
```

## 六、验证访问

浏览器打开（公网 IP 替换为实际值）：

```
http://1.15.240.71:4173/#/login
```

- 能打开登录页、可用管理员账号登录 → 部署成功。
- 后端健康检查：`http://1.15.240.71:4173/api/health`，返回 `{"code":0,"msg":"ok",...}` 即正常。

## 七、常用运维命令

```bash
# 停止服务
sudo docker compose down

# 重启服务
sudo docker compose restart

# 重新构建（改了代码后）
sudo docker compose up -d --build

# 查看容器列表
sudo docker ps
```

## 八、端口与网络说明

| 容器 | 内部端口 | 宿主机映射 | 是否对公网 |
|---|---|---|---|
| frontend（Nginx） | 80 | 4173 | 是，网站入口 |
| backend（Flask） | 5000 | 不映射，仅容器网络内互通 | 否，由前端反代 |
| MySQL | 3306 | 不映射 | 否，仅本机/宿主机内网 |

## 九、已知限制

- 模型训练功能（`/api/train`）依赖独立的 TensorFlow 环境（train_env），当前后端容器未包含 TensorFlow；网页训练转 TFLite 功能在容器内不可用，其余分拣、设备接入、记录查看等功能正常。
- 上传的图片持久化在 `./backend/uploads`，容器重建不会丢失。
