# 卸载「开机自启动后端」计划任务
#
# 运行：powershell -ExecutionPolicy Bypass -File deploy\uninstall_autostart.ps1

$TaskName = 'OpenMV-FruitSorting-Backend'

$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if (-not $task) {
    Write-Host "没有找到任务 $TaskName，无需卸载。"
    return
}

Write-Host "停止并删除任务：$TaskName"
Stop-ScheduledTask   -TaskName $TaskName -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
Write-Host "已删除。之后需要手动启动后端："
Write-Host '  cd C:\Users\10149\Desktop\openMV\backend'
Write-Host '  .\venv\Scripts\python.exe app.py'
