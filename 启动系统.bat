@echo off
chcp 936 >nul
title OpenMV 果实智能分拣系统 - 一键启动
setlocal

set "ROOT=C:\Users\10149\Desktop\openMV"
set "NODE=D:\5\node.exe"
set "PW=powershell -NoProfile -ExecutionPolicy Bypass -Command"

echo.
echo ================================================================
echo    OpenMV 果实智能分拣系统  -  一键启动
echo ================================================================
echo.

echo [1/4] 检查 MySQL 数据库 ...
%PW% "if((Get-Service MySQL80 -ErrorAction SilentlyContinue).Status -eq 'Running'){exit 0}else{exit 1}"
if errorlevel 1 goto start_mysql
echo        MySQL 运行中
goto backend

:start_mysql
echo        MySQL 未运行，正在尝试启动 ...
net start MySQL80 >nul 2>&1
%PW% "if((Get-Service MySQL80 -ErrorAction SilentlyContinue).Status -eq 'Running'){exit 0}else{exit 1}"
if errorlevel 1 (
    echo.
    echo        [失败] 无法启动 MySQL80，一般是权限不足。
    echo               请右键本文件，选择「以管理员身份运行」后重试；
    echo               或打开 services.msc 手动启动 MySQL80。
    echo.
    pause
    exit /b 1
)
echo        MySQL 已启动

:backend
echo.
echo [2/4] 启动后端服务，端口 5000 ...
%PW% "if(Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue){exit 0}else{exit 1}"
if errorlevel 1 goto start_backend
echo        后端已在运行，跳过
goto frontend

:start_backend
schtasks /run /tn "OpenMV-FruitSorting-Backend" >nul 2>&1
echo        已发出启动指令，等待就绪 ...
%PW% "$ok=$false; for($i=0; $i -lt 40; $i++){ try{ $r=Invoke-WebRequest 'http://127.0.0.1:5000/api/health' -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop; if($r.StatusCode -eq 200){ $ok=$true; break } } catch { Start-Sleep -Milliseconds 800 } }; if($ok){exit 0}else{exit 1}"
if errorlevel 1 (
    echo.
    echo        [失败] 后端 40 秒内未就绪。手动排查：
    echo               cd /d "%ROOT%"
    echo               backend\venv\Scripts\python.exe deploy\start_waitress.py
    echo.
    pause
    exit /b 1
)
echo        后端就绪

:frontend
echo.
echo [3/4] 启动前端服务，端口 5173 ...
%PW% "if(Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue){exit 0}else{exit 1}"
if errorlevel 1 goto start_frontend
echo        前端已在运行，跳过
goto openpage

:start_frontend
cd /d "%ROOT%\frontend"
start "Vite 前端服务" "%NODE%" "node_modules\vite\bin\vite.js" --host 0.0.0.0 --port 5173
echo        已启动 Vite，标题为 Vite 前端服务 的窗口请勿关闭
%PW% "$ok=$false; for($i=0; $i -lt 30; $i++){ try{ $r=Invoke-WebRequest 'http://127.0.0.1:5173' -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop; if($r.StatusCode -eq 200){ $ok=$true; break } } catch { Start-Sleep -Milliseconds 800 } }; if($ok){exit 0}else{exit 1}"
if errorlevel 1 (
    echo.
    echo        [失败] 前端 25 秒内未就绪，去看 Vite 窗口里的红色报错。
    echo.
    pause
    exit /b 1
)
echo        前端就绪

:openpage
echo.
echo [4/4] 打开浏览器 ...
start "" "http://localhost:5173/#/login"

echo.
echo ================================================================
echo    启动完成
echo.
echo    本机访问   : http://localhost:5173/#/login
echo    登录账号   : admin / admin123
echo                 操作员 operator1 / op123456
echo.
echo    局域网地址，给 OpenMV 板子或手机用:
%PW% "$a=Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue; $c=@(); foreach($x in $a){ if($x.IPAddress -notlike '127.*' -and $x.IPAddress -notlike '169.254.*' -and $x.InterfaceAlias -notlike '*VMware*' -and $x.InterfaceAlias -notlike '*Loopback*'){ $c += $x } }; if($c.Count -gt 0){ Write-Host ('                 http://' + $c[0].IPAddress + ':5173') } else { Write-Host '                 未取到局域网地址，请用 ipconfig 自行查看' }"
echo.
echo    数据库密码是 Aa123456. 末尾带点号，别和登录密码 admin123 混用
echo ================================================================
echo.
pause