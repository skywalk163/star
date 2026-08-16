<#
.SYNOPSIS
检查群星 Star API 服务状态
#>

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$PidFile = Join-Path $ProjectRoot "logs\star.pid"
$LogFile = Join-Path $ProjectRoot "logs\star.log"

Write-Host "=== 群星 Star 状态 ===" -ForegroundColor Cyan

# PID 检查（$Pid 是只读自动变量，改用 $ServerPid）
if (Test-Path $PidFile) {
    $ServerPid = Get-Content $PidFile -Raw -ErrorAction SilentlyContinue
    if ($ServerPid) {
        $ServerPid = $ServerPid.Trim()
        $Process = Get-Process -Id $ServerPid -ErrorAction SilentlyContinue
        if ($Process) {
            Write-Host "服务状态: 运行中 (PID: $ServerPid)" -ForegroundColor Green
            Write-Host "进程名称: $($Process.ProcessName)" -ForegroundColor Gray
            Write-Host "内存使用: $([math]::Round($Process.WorkingSet64 / 1MB, 1)) MB" -ForegroundColor Gray
            Write-Host "启动时间: $($Process.StartTime)" -ForegroundColor Gray
        } else {
            Write-Host "服务状态: PID 文件存在但进程已退出" -ForegroundColor Yellow
        }
    }
} else {
    Write-Host "服务状态: 未运行" -ForegroundColor Yellow
}

# 端口检查
$Connections = Get-NetTCPConnection -LocalPort 8765 -ErrorAction SilentlyContinue
if ($Connections) {
    Write-Host "端口 8765: 已监听" -ForegroundColor Green
} else {
    Write-Host "端口 8765: 未监听" -ForegroundColor Gray
}

# 日志信息
if (Test-Path $LogFile) {
    $LogSize = (Get-Item $LogFile).Length / 1KB
    $LogLines = (Get-Content $LogFile -Tail 3 -ErrorAction SilentlyContinue) -join "; "
    Write-Host "日志文件: $( [math]::Round($LogSize, 1) ) KB" -ForegroundColor Gray
    Write-Host "最新日志: $LogLines" -ForegroundColor DarkGray
}

# 日志目录大小
$LogDir = Join-Path $ProjectRoot "logs"
if (Test-Path $LogDir) {
    $TotalSize = (Get-ChildItem $LogDir -File | Measure-Object Length -Sum).Sum / 1KB
    Write-Host "日志目录: $( [math]::Round($TotalSize, 1) ) KB / 5 个文件" -ForegroundColor Gray
}