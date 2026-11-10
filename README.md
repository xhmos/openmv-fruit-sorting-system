# OpenMV 果实智能分拣监控管理系统

基于 OpenMV 的果实智能分拣监控管理系统，Flask 后端 + Vue 前端，实现图像识别、分拣记录、实时监控。

课程项目 / 教学演示用途。后端采用 Flask + waitress，前端 Vue 3 + Vite，数据落 MySQL 8。

## 功能模块

| 模块 | 说明 |
|---|---|
| 登录与权限 | JWT 鉴权，管理员 / 操作员两级角色，登录接口限流 |
| 用户管理 | 新增、编辑、禁用、删除用户，管理员专属 |
| 设备连接 | 摄像头 / 串口 / 网络流三类设备扫描、保存、连接、探测 |
| 实时看板 | 摄像头画面实时预览、启动/停止采集、分拣统计、录像文件列表 |
| 分拣记录 | 记录列表、筛选、图片查看、导出 Excel、批量删除 |
| 参数设置 | HSV 阈值、最小面积、置信度门槛、冷却时间在线调整 |
| 个人中心 | 头像上传/更换/移除、账号信息查看 |
| OpenMV 端 | `openmv_script/main.py` 为板端脚本，含 WiFi 上报与图像采集逻辑 |

## 技术栈

**后端**：Flask、Flask-SQLAlchemy、Flask-JWT-Extended、Flask-SocketIO、waitress、PyMySQL、OpenCV（headless）、openpyxl

**前端**：Vue 3、Vite、Element Plus、ECharts、Axios、socket.io-client

**数据库**：MySQL 8（库名 `openmv_ai`，四张表：`user` / `sort_record` / `detect_record` / `sys_setting` / `saved_device`）

## 目录结构

```
openMV/
├─ backend/                   Flask 后端
│  ├─ app.py                  应用工厂，蓝图注册，计划任务
│  ├─ config.py               配置读取（环境变量）
│  ├─ models.py               ORM 模型
│  ├─ routes/                 接口蓝图（auth/user/record/device/system/setting）
│  ├─ services/               camera_service 摄像头采集与分拣服务
│  ├─ utils/                  日志、安全、Excel 导出、文件清理
│  ├─ tests/                  pytest 接口测试
│  ├─ requirements.txt
│  └─ .env.example            环境变量模板（复制为 .env 后填写）
├─ frontend/                  Vue 3 前端
│  ├─ src/views/              登录、看板、记录、设备、设置、用户管理、个人中心
│  ├─ src/api/                接口封装与 axios 拦截器
│  └─ vite.config.js
├─ deploy/                    waitress 启动脚本、开机自启脚本、nginx 示例
├─ openmv_script/main.py      OpenMV 板端脚本
├─ pc_camera_device.py        PC 摄像头模拟设备（联调用）
├─ simulate_device.py         模拟上报设备（联调用）
├─ 使用手册.md
├─ 系统实施与开发指南.md
├─ 安全自测报告.md
└─ 工程化整改说明.md
```

## 快速开始

### 1. 准备数据库

```sql
CREATE DATABASE openmv_ai DEFAULT CHARSET utf8mb4;
```

### 2. 配置环境变量

```bash
cd backend
copy .env.example .env
```

按实际情况填写 `DB_USER` / `DB_PASSWORD` / `DB_HOST` / `DB_PORT` / `DB_NAME`，以及 `SECRET_KEY`、`JWT_SECRET`、`DEVICE_TOKEN`。

`.env` 已被 `.gitignore` 排除，不会进入版本库。

### 3. 启动后端

```bash
cd backend
python -m venv venv
venv\Scripts\pip install -r requirements.txt
venv\Scripts\python app.py
```

默认监听 `0.0.0.0:5000`，健康检查 `GET /api/health`。

生产方式可用 waitress：

```bash
venv\Scripts\python deploy\start_waitress.py
```

### 4. 启动前端

```bash
cd frontend
npm install
npm run dev
```

访问 `http://localhost:5173`。

## 默认账号

| 账号 | 密码 | 角色 |
|---|---|---|
| admin | 见 `DEFAULT_ADMIN_PASSWORD` 或首次启动时自动创建 | 管理员 |
| operator1 | 需自行创建 | 操作员 |

设备上报请求头：`X-Device-Token: <DEVICE_TOKEN>`

## 设备接入

- **摄像头**：填编号（`0` 为默认摄像头）或网络流地址；填 Windows 设备名时会自动在 0~4 号索引间匹配
- **串口**：目前仅做枚举与探测，未实现向执行机构下发指令
- **板端**：`openmv_script/main.py` 烧录到 OpenMV 后按 WiFi 配置上报 `/api/device/report`

## 已知限制

1. **果实识别为 HSV 颜色阈值分割，不是神经网络**。仓库内的 `FRUITS` 预设是演示值，对真实果实需要重新标定，否则会把室内人脸、桌面误判为水果。
2. **板端部署未完成**。OpenMV 与电脑之间目前只能识别到 CH340 串口，打开报权限错误，固件烧录、模型上传、板端推理均未实测。
3. `detect_record` 表仅在库中存在，未做 ORM 映射。
4. 前端各页面仅经接口联调与编译校验，未做完整浏览器端视觉回归。

## 文档

见根目录 `使用手册.md`、`系统实施与开发指南.md`、`安全自测报告.md`、`工程化整改说明.md`。
