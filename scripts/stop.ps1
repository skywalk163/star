<#
.SYNOPSIS
停止群星 Star API 服务
#>

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$PidFile = Join-Path $ProjectRoot "logs\star.pid"
$LogDir = Join-Path $ProjectRoot "logs"

if (-not (Test-Path $PidFile)) {
    Write-Host "[星辉] 服务未在运行" -ForegroundColor Yellow
    exit 0
}

$Pid = Get-Content $PidFile -Raw -ErrorAction SilentlyContinue
if ($Pid) {
    $Pid = $Pid.Trim()
    try {
        $Process = Get-Process -Id $Pid -ErrorAction Stop
        if ($Process.ProcessName -eq "python") {
            Stop-Process -Id $Pid -Force -ErrorAction SilentlyContinue
            Write-Host "[星辉] 服务已停止 (PID: $Pid)" -ForegroundColor Green
        }
    } catch {
        Write-Host "[星辉] 进程已退出 (PID: $Pid)" -ForegroundColor Gray
    }
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
}

# 也尝试停止所有 uvicorn 子进程
Get-Process -Name "python" -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -match "uvicorn" -and $_.CommandLine -match "star_api"
} | Stop-Process -Force -ErrorAction SilentlyContinue