@echo off
chcp 936 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"
title OpenMV 果实分拣系统 - 内网穿透（cpolar）

set "CPOLAR=D:\cpolar\cpolar.exe"
if not exist "%CPOLAR%" for /f "delims=" %%i in ('where cpolar 2^>nul') do set "CPOLAR=%%i"
if not exist "%CPOLAR%" (
  echo   没找到 cpolar.exe，请先安装：https://www.cpolar.com/
  pause
  exit /b 1
)

set "NODE=D:\5\node.exe"
if not exist "%NODE%" set "NODE=node"
set "MODE=prod"
set "PORT=4173"
set "PCMD=preview"
if /i "%~1"=="dev" (
  set "MODE=dev"
  set "PORT=5173"
  set "PCMD="
)

set "LOGDIR=%~dp0logs"
if not exist "%LOGDIR%" mkdir "%LOGDIR%"
set "CLOG=%LOGDIR%\cpolar.log"
set "PLOG=%LOGDIR%\preview.log"
set "URLFILE=%~dp0公网地址.txt"

echo ============================================
echo    OpenMV 果实智能分拣系统 - 公网演示
echo ============================================
echo    [隧道] cpolar    [模式] %MODE%    端口 %PORT%
echo.


if "%MODE%"=="prod" (
  echo [1/3] 打包前端，首次约 30 秒...
  pushd "%~dp0frontend"
  "%NODE%" node_modules\vite\bin\vite.js build
  if errorlevel 1 (
    popd
    echo   打包失败，公网演示无法继续。
    pause
    exit /b 1
  )
  popd
) else (
  echo [1/3] 开发模式，跳过打包
)

echo [2/3] 检查 %PORT% 端口...
netstat -ano | findstr /r /c:"TCP.*:%PORT%.*LISTENING" >nul
if errorlevel 1 (
  echo       未运行，正在后台启动前端...
  start /b "" "%NODE%" node_modules\vite\bin\vite.js %PCMD% --host 0.0.0.0 --port %PORT% > "%PLOG%" 2>&1
  timeout /t 7 /nobreak >nul
  netstat -ano | findstr /r /c:"TCP.*:%PORT%.*LISTENING" >nul
  if errorlevel 1 (
    echo       启动失败，日志见 logs\preview.log
    pause
    exit /b 1
  )
)
echo       前端已就绪

netstat -ano | findstr /r /c:"TCP.*:5000.*LISTENING" >nul
if errorlevel 1 (
  echo [注意] 后端 5000 没在运行，登录会失败，请先运行 启动系统.bat
)

echo [3/3] 建立 cpolar 隧道，等待公网地址...
if exist "%CLOG%" del "%CLOG%"
powershell -NoProfile -Command "Start-Process -FilePath '%CPOLAR%' -ArgumentList 'http','%PORT%','--log=stdout' -RedirectStandardOutput '%CLOG%' -RedirectStandardError '%CLOG%.err' -NoNewWindow"

set "URL="
for /f "delims=" %%u in ('powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\get_cpolar_url.ps1" -LogPath "%CLOG%"') do set "URL=%%u"

if not defined URL (
  echo.
  echo   没能拿到地址，最后 15 行日志：
  powershell -NoProfile -Command "Get-Content -Path '%CLOG%' -Tail 15"
  echo.
  echo   常见原因：
  echo     1. 免费版同时只能跑 2 条隧道，先在 cpolar 后台停掉不用的；
  echo     2. 刚重启过，等 30 秒再试；
  echo     3. 账号 authtoken 失效，去 cpolar 后台重新复制并执行 cpolar authtoken xxx。
  pause
  exit /b 1
)

> "%URLFILE%" echo %URL%
echo.
echo   ==================================================
echo     公网地址： %URL%
echo   ==================================================
echo     已保存到： 公网地址.txt
echo     手机用流量即可打开，电脑也可以。
echo     这个窗口不要关，关掉后地址立即失效。
echo.
pause
echo 关闭本窗口即断开隧道。
endlocal