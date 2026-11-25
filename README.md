# OpenMV 果实智能分拣监控管理系统
# OpenMV Fruit Sorting Monitoring & Management System

> 基于 OpenMV 的果实智能分拣监控管理系统：Flask 后端 + Vue 3 前端 + MySQL 8，实现图像识别、分拣记录、实时监控与设备接入。
>
> A fruit sorting monitoring system based on OpenMV: Flask backend + Vue 3 frontend + MySQL 8, covering image recognition, sorting records, real-time monitoring and device access.

课程项目 / 教学演示用途。后端 Flask，前端 Vue 3 + Vite，数据落 MySQL 8，实时推送基于 Flask-SocketIO。
Course project / teaching demo. Flask backend, Vue 3 + Vite frontend, MySQL 8 persistence, real-time push via Flask-SocketIO.

---

## 一、功能模块 / Features

| 模块 Module | 中文说明 | English Description |
|---|---|---|
| 登录与权限 Auth & Permissions | JWT 鉴权，管理员 / 操作员两级角色，登录接口限流 | JWT authentication, two roles (admin / operator), login rate limiting |
| 用户管理 User Management | 新增、编辑、禁用、删除用户，仅管理员可用 | Create / edit / disable / delete users, admin only |
| 设备连接 Device Connection | 摄像头、串口、网络流三类设备扫描、保存、连接、探测 | Scan, save, connect and probe cameras / serial ports / network streams |
| 实时看板 Live Dashboard | 画面实时预览、启停采集、分拣统计、录像列表，SocketIO 实时推送 | Live preview, start/stop capture, sorting stats, video list, real-time SocketIO push |
| 分拣记录 Sort Records | 记录列表、筛选、图片查看、导出 Excel、批量删除 | Record list, filters, image preview, Excel export, batch delete |
| 参数设置 Parameters | HSV 阈值、最小面积、置信度门槛、冷却时间在线调整 | Online tuning of HSV thresholds, min area, confidence threshold, cooldown |
| 个人中心 Profile | 头像上传 / 更换 / 移除、账号信息查看 | Avatar upload / change / remove, account info view |
| 板端分拣 On-device Sorting | OpenMV 板端脚本加载 TFLite 模型分类，`train/` 为完整训练链 | OpenMV board script loads TFLite model; `train/` holds the full training chain |
| 手机端 Mobile App | Flutter 应用复用同一套后端接口 | Flutter app reusing the same backend API |

---

## 二、技术栈 / Tech Stack

**后端 Backend**：Flask、Flask-SQLAlchemy、Flask-Bcrypt、Flask-Limiter、Flask-SocketIO、PyMySQL、OpenCV（headless）、openpyxl；生产服务器由 **gunicorn + eventlet** 承载。
Flask, Flask-SQLAlchemy, Flask-Bcrypt, Flask-Limiter, Flask-SocketIO, PyMySQL, headless OpenCV, openpyxl; served in production by **gunicorn + eventlet**.

**前端 Frontend**：Vue 3、Vite、Vue Router（hash 路由）、Pinia、Element Plus、ECharts、Axios、socket.io-client。
Vue 3, Vite, Vue Router (hash history), Pinia, Element Plus, ECharts, Axios, socket.io-client.

**数据库 Database**：MySQL 8，业务库 `openmv_ai`，五张表：`user` / `sort_record` / `sys_setting` / `saved_device` / `operation_log`。
MySQL 8, database `openmv_ai`, five tables: `user` / `sort_record` / `sys_setting` / `saved_device` / `operation_log`.

**部署 Deploy**：Docker Compose 编排（前端 Nginx + 后端容器），移动端 Flutter。
Docker Compose (frontend Nginx + backend container), Flutter mobile client.

---

## 三、目录结构 / Directory Layout

```
openMV/
├─ backend/                  Flask 后端 / Flask backend
│  ├─ app.py                 应用工厂、蓝图注册、SocketIO 握手鉴权
│  ├─ extensions.py          db / bcrypt / socketio / limiter 集中初始化
│  ├─ models.py              ORM 模型（5 张表）/ ORM models (5 tables)
│  ├─ wsgi.py                生产入口 gunicorn + eventlet / production entry
│  ├─ routes/                蓝图 auth/device/record/setting/system/train/user
│  ├─ services/              camera_service 采集与分拣服务 / capture & sorting service
│  ├─ utils/                 日志、鉴权、Excel 导出、文件清理 / logging, auth, export, cleanup
│  └─ requirements.txt
├─ frontend/                 Vue 3 前端 / Vue 3 frontend
│  ├─ src/views/             Login / Dashboard / Record / Device / Setting / UserManage / Profile
│  ├─ src/api/               axios 实例与接口封装 / axios instance & API wrappers
│  ├─ src/router/            hash 路由与守卫 / hash router & guards
│  ├─ src/store/             Pinia 登录态 / Pinia auth state
│  └─ src/utils/socket.js    SocketIO 单例客户端 / singleton SocketIO client
├─ deploy/                   Dockerfile、Nginx 反代、部署指南 / Dockerfiles, nginx, deploy guide
├─ train/                    实验五训练链：采集/划分/训练/量化/验证 / training chain
├─ openmv_script/            OpenMV 板端脚本 main.py / nn_classify.py
├─ mobile_app/               Flutter 手机端工程 / Flutter mobile project
├─ scripts/                  内网穿透地址获取等辅助脚本 / helper scripts
├─ docs/samples/             样例截图 / sample screenshots
├─ assets/                   说明页离线图表库 echarts.min.js / offline chart library
├─ 代码框架鱼骨图.html         代码架构鱼骨图（节点骨架 + 连接关系）/ code framework fishbone
├─ 搭建指南.html              环境准备到上线的搭建步骤 / step-by-step setup guide
├─ simulate_device.py        模拟上报设备（联调）/ simulated reporting device
└─ pc_camera_device.py        PC 摄像头模拟设备（联调）/ PC camera simulator
```

---

## 四、快速开始 / Quick Start

### 1. 准备数据库 / Prepare the database

```sql
CREATE DATABASE openmv_ai DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### 2. 配置环境变量 / Configure environment variables

```bash
cd backend
copy .env.example .env      # Windows / Windows
# cp .env.example .env      # Linux / macOS
```

按实际情况填写 `DB_USER` / `DB_PASSWORD` / `DB_HOST` / `DB_PORT` / `DB_NAME`，以及 `SECRET_KEY`、`JWT_SECRET`、`DEVICE_TOKEN`。
Fill in `DB_USER` / `DB_PASSWORD` / `DB_HOST` / `DB_PORT` / `DB_NAME`, plus `SECRET_KEY`, `JWT_SECRET`, `DEVICE_TOKEN`.

`.env` 已被 `.gitignore` 排除，不会进入版本库。
`.env` is ignored by `.gitignore` and is never committed.

### 3. 启动后端 / Start the backend

```bash
cd backend
python -m venv venv
venv\Scripts\pip install -r requirements.txt   # Windows
venv\Scripts\python app.py                    # 开发模式 / dev mode
```

默认监听 `0.0.0.0:5000`，健康检查 `GET /api/health`。生产环境由 gunicorn + eventlet 经 `wsgi:app` 启动。
Listens on `0.0.0.0:5000` by default; health check `GET /api/health`. In production it runs under gunicorn + eventlet via `wsgi:app`.

### 4. 启动前端 / Start the frontend

```bash
cd frontend
npm install
npm run dev
```

访问 `http://localhost:5173`。Open at `http://localhost:5173`.

### 5. Docker 部署 / Docker deployment

在服务器项目根目录复制环境变量并填写数据库信息：
Copy the env file on the server root and fill in the database credentials:

```bash
cp .env.docker .env
# 编辑 .env：DB_USER / DB_PASSWORD / DB_NAME  / edit .env
docker compose up -d --build
```

- 前端容器：Nginx 托管打包产物，宿主机 `4173` → 容器 `80`，并反代 `/api`、`/uploads`、`/socket.io` 到后端。
  Frontend container: Nginx serves the build, host `4173` → container `80`, proxying `/api`, `/uploads`, `/socket.io` to the backend.
- 后端容器：gunicorn + eventlet 运行 Flask，内部端口 `5000` 仅在容器内网暴露。
  Backend container: gunicorn + eventlet runs Flask; internal port `5000` is exposed only on the internal network.

完整步骤见 [`deploy/DOCKER_DEPLOY.md`](deploy/DOCKER_DEPLOY.md)。
See [`deploy/DOCKER_DEPLOY.md`](deploy/DOCKER_DEPLOY.md) for the full guide.

---

## 五、默认账号 / Default Account

首次启动由配置 `DEFAULT_ADMIN_USER` / `DEFAULT_ADMIN_PASSWORD` 自动创建管理员；本地代码默认 `admin / admin123`，生产环境在 `.env` 中覆盖。
On first start an admin is created from `DEFAULT_ADMIN_USER` / `DEFAULT_ADMIN_PASSWORD`. The code default is `admin / admin123`; override it in `.env` in production.

设备上报请求头 / Device reporting header：`X-Device-Token: <DEVICE_TOKEN>`（默认 `openmv-device-2026`）。

| 账号 Account | 密码 Password | 角色 Role |
|---|---|---|
| admin | 见 `DEFAULT_ADMIN_PASSWORD`，或首次启动自动创建 / set in config | 管理员 Admin |
| operator1 | 需自行创建 / create manually | 操作员 Operator |

---

## 六、设备接入 / Device Access

- **摄像头 Camera**：填编号（`0` 为默认摄像头）或网络流地址；填 Windows 设备名时会自动在 0~4 号索引间匹配。
  Fill an index (`0` = default camera) or a network stream URL; a Windows device name is matched across indexes 0–4 automatically.
- **串口 Serial**：目前仅做枚举与探测，未实现向执行机构下发指令。
  Enumeration and probing only; no actuator command downlink yet.
- **板端 On-board**：`openmv_script/main.py` 烧录到 OpenMV 后按 WiFi 配置上报 `/api/device/report`。
  Flash `openmv_script/main.py` to the OpenMV; it reports to `/api/device/report` over WiFi per config.

---

## 七、神经网络训练链（实验五）/ Neural Network Training Chain (Lab 5)

`train/` 目录是完整的 采集 → 划分 → 训练 → 量化 → 验证 工具链，对应《实验五 OpenMV 神经网络训练》报告要求。
The `train/` directory is a complete collect → split → train → quantize → validate toolchain, matching the Lab 5 OpenMV neural network training report.

| 脚本 Script | 作用 Purpose | 关键参数 Key Params |
|---|---|---|
| `collect_dataset.py` | 采集数据集，输出 320×240 / collect dataset, 320×240 | `--per-class 60` |
| `split_dataset.py` | 7:2:1 划分，产出 manifest / split 7:2:1, emit manifest | `--seed 42` |
| `train_cnn.py` | 轻量 CNN 训练，96×96×3 / lightweight CNN, 96×96×3 | `--epochs 30 --batch 32 --lr 1e-3` |
| `convert_tflite.py` | 转 TFLite + INT8 全整数量化 / TFLite + INT8 quantization | `--calib 100` |
| `pc_infer.py` | PC 端 `tf.lite.Interpreter` 验证 / verify on PC interpreter | `--image` 或直接开摄像头 / or live camera |

```powershell
.\train_env\Scripts\python.exe train\collect_dataset.py --per-class 60
.\train_env\Scripts\python.exe train\split_dataset.py --clean
.\train_env\Scripts\python.exe train\train_cnn.py --epochs 30
.\train_env\Scripts\python.exe train\convert_tflite.py
.\train_env\Scripts\python.exe train\pc_infer.py --image dataset\raw\apple\apple_0001.jpg
```

**技术要点 / Key points**：
- 数据增强放在 `tf.data` 管道里，不放模型内，保证导出的模型干净、可转换。
  Augmentation lives in the `tf.data` pipeline, not inside the model, so the exported model stays clean and convertible.
- INT8 量化强制 `TFLITE_BUILTINS_INT8` + uint8 输入 + int8 输出，这是 OpenMV 能加载的形式。
  INT8 quantization forces `TFLITE_BUILTINS_INT8` with uint8 input and int8 output, the format OpenMV can load.
- 预处理统一为「直接拉伸到 96×96」，训练、PC 推理、量化校准三处一致，避免 PC 准而板端乱。
  Preprocessing uniformly stretches to 96×96 across training, PC inference and quantization calibration to avoid PC-good / board-bad.

**硬件前提 / Hardware requirement**：只有 **H7 Plus / RT1062（32MB SDRAM）** 能跑模型；标准 H7 仅 1MB SRAM 会 `MemoryError`。
Only **H7 Plus / RT1062 (32MB SDRAM)** can run the model; a standard H7 with 1MB SRAM raises `MemoryError`.

---

## 八、配套说明页 / Companion Pages

- [`搭建指南.html`](搭建指南.html)：从环境准备、软件安装、本地试运行到部署上线的分步指南。
  Step-by-step guide from environment setup and software install to local trial and deployment.
- [`代码框架鱼骨图.html`](代码框架鱼骨图.html)：代码架构鱼骨图，节点展示模块骨架代码与注释，连接关系展示两端调用实现。
  Fishbone diagram of the code architecture: nodes show module skeletons with comments, links show how two parts call each other.

---

## 九、已知限制 / Known Limitations

1. **果实识别为 HSV 颜色阈值分割，不是神经网络**。仓库内的 `FRUITS` 预设是演示值，对真实果实需要重新标定，否则会把室内人脸、桌面误判为水果。
   Recognition is HSV color thresholding, not a neural network. The bundled `FRUITS` presets are demo values and must be recalibrated for real fruit, otherwise faces or tables may be misclassified.
2. **板端部署未完成实测**。OpenMV 固件烧录、模型上传、板端推理均未在板子上验证。
   On-board deployment is not field-tested yet: firmware flashing, model upload and board-side inference are unverified on hardware.
3. **后端容器不含 TensorFlow**，网页训练 / 转 TFLite 功能在容器内不可用；训练需在带训练环境的机器上完成。
   The backend container does not ship TensorFlow, so web training / TFLite export is unavailable inside the container; training must run on a machine with the training environment.
4. 前端各页面经接口联调与编译校验，未做完整浏览器端视觉回归。
   Frontend pages passed API integration and build checks, but not a full visual regression in the browser.
