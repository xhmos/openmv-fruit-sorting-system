@echo off
chcp 936 >nul
setlocal
cd /d "%~dp0"
title OpenMV 果实分拣系统 - 对外演示

echo ============================================
echo    OpenMV 果实分拣系统 - 对外演示
echo ============================================
echo.

set "CF=%~dp0cloudflared.exe"
set "DL=https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
set "NODE=D:\5\node.exe"
if not exist "%NODE%" set "NODE=node"

rem ---- 模式：默认打包后的静态预览，手机加载快；传 dev 则穿透开发服务器方便调试
set "MODE=prod"
set "PORT=4173"
if /i "%~1"=="dev" (
  set "MODE=dev"
  set "PORT=5173"
)

echo [模式] %MODE% 端口 %PORT%
if "%MODE%"=="prod" echo         打包后的静态版本，别人打开快，适合对外演示
if "%MODE%"=="dev" echo         开发服务器，热更新方便，但手机上加载慢
echo.

rem ---------- 1/4 工具 ----------
if not exist "%CF%" (
  echo [1/4] 首次运行，下载 cloudflared.exe，约 53MB，请稍等...
  curl -L --max-time 600 -o "%CF%" "%DL%"
  if errorlevel 1 (
    echo.
    echo   下载失败。请开加速器后重试，或手动下载：
    echo   %DL%
    echo   放到本文件同目录后重新双击。
    pause
    exit /b 1
  )
) else (
  echo [1/4] cloudflared 已就绪
)

rem ---------- 2/4 打包 ----------
echo [2/4] 打包前端，通常两三秒...
if "%MODE%"=="prod" goto DO_BUILD
echo       开发模式，跳过打包
goto PORT_CHECK

:DO_BUILD
pushd "%~dp0frontend"
"%NODE%" node_modules\vite\bin\vite.js build
if errorlevel 1 (
  popd
  echo.
  echo   打包失败，把上面的报错发给我。
  pause
  exit /b 1
)
popd
echo       打包完成

rem ---------- 3/4 启动服务 ----------
:PORT_CHECK
echo [3/4] 检查端口 %PORT% ...
netstat -ano | findstr /r /c:"TCP.*:%PORT%.*LISTENING" >nul
if not errorlevel 1 (
  echo       已在运行，直接复用
  goto BACKEND_CHECK
)

echo       未运行，正在启动服务...
if "%MODE%"=="prod" start "" /min /d "%~dp0frontend" "%NODE%" node_modules\vite\bin\vite.js preview --host 0.0.0.0 --port %PORT%
if "%MODE%"=="dev" start "" /min /d "%~dp0frontend" "%NODE%" node_modules\vite\bin\vite.js --host 0.0.0.0 --port %PORT%
timeout /t 6 /nobreak >nul

netstat -ano | findstr /r /c:"TCP.*:%PORT%.*LISTENING" >nul
if errorlevel 1 (
  echo.
  echo   端口 %PORT% 没起来。多半是 node 路径不对，当前用的是 %NODE%
  pause
  exit /b 1
)
echo       服务已就绪

:BACKEND_CHECK
netstat -ano | findstr /r /c:"TCP.*:5000.*LISTENING" >nul
if errorlevel 1 (
  echo.
  echo   [注意] 后端 5000 没在运行，页面能打开但登录会失败。
  echo          请先双击「启动系统.bat」把 MySQL 和后端拉起来。
  echo.
)

rem ---------- 4/4 隧道 ----------
echo [4/4] 建立隧道...
echo.
echo   下面那行 https://xxxx.trycloudflare.com 就是公网地址
echo   发给别人，手机用流量也能直接打开
echo   关掉这个窗口 = 断开隧道
echo --------------------------------------------
"%CF%" tunnel --url http://127.0.0.1:%PORT% --no-autoupdate

echo.
echo 隧道已结束。
pause