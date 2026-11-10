# 上线部署说明

## 一、项目现在是什么状态

开发模式：`backend/app.py` 用 Werkzeug 跑，`debug=True`，前端 `npm run dev`。
**这套配置绝对不能直接对公网开放**（调试器可执行任意代码）。

## 二、部署前必须做的 6 件事

### 1. 换掉所有密钥

`backend\.env` 里这两项必须是随机长串，不能沿用开发值：

```ini
SECRET_KEY=<随机 32 字节以上>
JWT_SECRET=<随机 32 字节以上，且与 SECRET_KEY 不同>
```

生成命令：

```powershell
.\backend\venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

> 注意：`JWT_SECRET` 少于 32 字节时 PyJWT 会报 `InsecureKeyLengthWarning`，别留短密钥。

### 2. 关掉 debug

```powershell
$env:FLASK_DEBUG='0'
```

`app.py` 和 `deploy\start_waitress.py` 都已支持该环境变量。

### 3. 收紧跨域白名单

`CORS_ORIGINS` 只写真实前端域名，例如：

```ini
CORS_ORIGINS=https://fruit.your-domain.com
```

（`config.py` 会自动补上本机网卡的 5173 端口，那是为了方便局域网演示；
正式环境不要用 5173 端口对外。）

### 4. 换掉默认设备令牌

`DEVICE_TOKEN` 改成随机串，并同步改 `openmv_script\main.py` 里的 `DEVICE_TOKEN`。
否则任何人知道默认值就能伪造设备上报。

### 5. 前端打包

```powershell
cd C:\Users\10149\Desktop\openMV\frontend
npm run build
```

产物在 `frontend\dist`，交给 Nginx 托管。

> 打包前如果前后端不同域，先在 `frontend\.env.production` 写：
> ```
> VITE_API_BASE=https://fruit.your-domain.com
> ```
> 同域反代则不用写（前端会按当前主机名推导）。

### 6. 后端用 waitress 启动

```powershell
cd C:\Users\10149\Desktop\openMV
.\backend\venv\Scripts\python.exe deploy\start_waitress.py
```

- 默认监听 `0.0.0.0:5000`，可用 `HOST` / `PORT` / `THREADS` 覆盖
- 日志在 `backend\logs\app.log`，按天轮转保留 14 天
- 启动时会打印跨域白名单，方便核对

## 三、Nginx把 `deploy\nginx.conf.example` 拷到 Nginx 配置目录，改三处后 reload：

1. `server_name` 换成你的域名
2. `root` 换成实际的 `frontend\dist` 路径
3. `client_max_body_size` 保持 3m，与后端 `MAX_CONTENT_LENGTH` 对齐

```powershell
nginx -t          # 先校验语法
nginx -s reload
```

## 四、开机自启动（可选，本机已验证）

想让「登录 Windows 后后端自动跑起来」，不用每次手动开一个窗口：

```powershell
powershell -ExecutionPolicy Bypass -File deploy\install_autostart.ps1
```

脚本会做四件事：

1. 检查 5000 端口，若被旧的后端进程占着就先停掉（避免任务一启动就端口冲突）；
2. 注册计划任务 `OpenMV-FruitSorting-Backend`，触发器是「当前用户登录时」；
3. 立即启动一次并做健康检查，OK 才报成功；
4. 打印任务状态和后续命令。

几个要点：

- **不需要管理员权限**：用的是当前用户身份，权限与手动启动完全一致（开机触发那种需要管理员，而且跑在无网络会话里，连 MySQL 反而更容易失败）。
- **没有窗口**：计划任务在后台跑，不会像启动文件夹那样弹一个黑框。
- **不会 72 小时被杀**：`ExecutionTimeLimit` 已设为 0（默认是 3 天，服务类任务必须改，否则跑到第三天会莫名停止）。
- **失败会重试**：配置了失败后 1 分钟重试、最多 3 次。

常用命令：

```powershell
Get-ScheduledTask -TaskName 'OpenMV-FruitSorting-Backend'          # 看状态
Stop-ScheduledTask -TaskName 'OpenMV-FruitSorting-Backend'         # 临时停
Start-ScheduledTask -TaskName 'OpenMV-FruitSorting-Backend'        # 临时起
powershell -File deploy\uninstall_autostart.ps1                    # 彻底取消
```

> 只接管**后端**。前端 `npm run dev` 仍然手动启动（开发时的热更新本来就需要它在终端里跑）。
> 如果改成 `npm run build` + Nginx 托管，前端由 Nginx 服务管理，也就不需要开机脚本了。

---

## 五、已知限制（答辩时可以主动说）

| 限制 | 说明 |
|---|---|
| 传输层依赖服务器能力 | 本机实测 **waitress 3.0.2 + simple-websocket 可完成 WebSocket 升级**（客户端 transport 实际为 websocket，推送、MJPEG 均正常）。换到某些不透传 WSGI socket 的服务器时会自动退化为长轮询，功能不受影响 |
| 图片无限增长 | 已内置清理线程：默认保留 90 天、最多 2000 张（`IMAGE_RETENTION_DAYS` / `IMAGE_MAX_FILES` 可调） |
| 单机部署 | 没有做多实例；多实例时 SocketIO 需要消息队列（Redis），内存限流也要换成 Redis 存储 |
| 没有 HTTPS | 生产必须上证书，否则 JWT 在网络上是明文传输 |

## 六、部署后的验收清单

```powershell
# 1. 健康检查
curl.exe https://fruit.your-domain.com/api/health

# 2. 未登录必须 401
curl.exe -i https://fruit.your-domain.com/api/record/list

# 3. 登录拿 token
curl.exe -X POST https://fruit.your-domain.com/api/auth/login -H "Content-Type: application/json" -d "{\"username\":\"admin\",\"password\":\"<你的密码>\"}"

# 4. 跨域：恶意来源不应拿到 ACAO 头
curl.exe -i -H "Origin: https://evil.com" https://fruit.your-domain.com/api/health
```

再打开网页，确认：看板出图、实时推送更新、记录页能翻页、导出能下载。
