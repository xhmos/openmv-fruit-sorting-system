# 安装「开机自启动后端」计划任务
#
# 做什么：登录 Windows 后自动用 waitress 启动后端（无窗口、常驻），
#         这样开机后前端一打开就有数据，不用每次手动起 python。
#
# 为什么用「登录时触发」而不是「开机触发」：
#   开机触发需要管理员权限且运行在无网络会话里，MySQL 连接和文件路径更容易出问题；
#   登录触发用当前用户身份、权限与手动启动完全一致，最稳。
#
# 运行方式（不需要管理员）：
#   powershell -ExecutionPolicy Bypass -File deploy\install_autostart.ps1
#
# 卸载：deploy\uninstall_autostart.ps1

$ErrorActionPreference = 'Stop'

$TaskName = 'OpenMV-FruitSorting-Backend'
$Root     = Split-Path -Parent $PSScriptRoot          # deploy 的上一级 = 项目根
$Python   = Join-Path $Root 'backend\venv\Scripts\python.exe'
$Script   = Join-Path $Root 'deploy\start_waitress.py'
$Port     = 5000

if (-not (Test-Path -LiteralPath $Python)) { throw "找不到 venv 里的 python：$Python" }
if (-not (Test-Path -LiteralPath $Script)) { throw "找不到启动脚本：$Script" }

Write-Host "[1/4] 检查端口 $Port 是否被占用..."
$busy = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($busy) {
    $pidInUse = ($busy.OwningProcess | Select-Object -First 1)
    $owner = (Get-Process -Id $pidInUse -ErrorAction SilentlyContinue).ProcessName
    Write-Host "      端口被 $owner (pid=$pidInUse) 占用，先停掉，避免任务启动即失败"
    if ($owner -match 'python') {
        Stop-Process -Id $pidInUse -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
    } else {
        throw "端口 $Port 被 $owner 占用，请先手动关掉它再执行本脚本"
    }
} else {
    Write-Host "      端口空闲"
}

Write-Host "[2/4] 注册计划任务：$TaskName"
$action = New-ScheduledTaskAction -Execute $Python -Argument "`"$Script`"" -WorkingDirectory $Root
$trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
# ExecutionTimeLimit 必须为 0，否则默认 72 小时后任务会被系统强杀
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -MultipleInstances IgnoreNew

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description 'OpenMV 果实分拣系统后端（waitress，登录后自动启动）' `
    -Force | Out-Null
Write-Host "      已注册"

Write-Host "[3/4] 立即启动一次做验证..."
Start-ScheduledTask -TaskName $TaskName
Start-Sleep -Seconds 9

$listen = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
$health = $null
try { $health = curl.exe -s "http://127.0.0.1:$Port/api/health" } catch { $health = $null }

Write-Host "[4/4] 结果"
if ($listen -and $health -match '"code":\s*0') {
    Write-Host "      OK：端口 $Port 已监听，健康检查正常"
    Write-Host "      任务状态：" + (Get-ScheduledTask -TaskName $TaskName).State
    Write-Host ""
    Write-Host "以后开机登录 Windows 就会自动跑起来，不用再手动启动后端。"
    Write-Host "临时停掉：Stop-ScheduledTask -TaskName '$TaskName'"
    Write-Host "彻底取消：powershell -File deploy\uninstall_autostart.ps1"
} else {
    Write-Host "      失败：端口未监听或健康检查异常"
    Write-Host "      最近一次任务结果：" + ((Get-ScheduledTaskInfo -TaskName $TaskName).LastTaskResult)
    Write-Host "      排查：手动跑一次 deploy\start_waitress.py 看报什么错"
    exit 1
}
