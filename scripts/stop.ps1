<#
.SYNOPSIS
停止群星 Star API 服务
#>

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$PidFile = Join-Path $ProjectRoot "logs\star.pid"

if (-not (Test-Path $PidFile)) {
    Write-Host "[星辉] 服务未在运行" -ForegroundColor Yellow
    exit 0
}

# 注意：$Pid 是 PowerShell 只读自动变量，必须换名
$ServerPid = Get-Content $PidFile -Raw -ErrorAction SilentlyContinue
if ($ServerPid) {
    $ServerPid = $ServerPid.Trim()
    try {
        $Process = Get-Process -Id $ServerPid -ErrorAction Stop
        if ($Process.ProcessName -match "python") {
            Stop-Process -Id $ServerPid -Force -ErrorAction SilentlyContinue
            Write-Host "[星辉] 服务已停止 (PID: $ServerPid)" -ForegroundColor Green
        } else {
            Write-Host "[星辉] PID $ServerPid 不是 Star 服务进程 ($($Process.ProcessName))，跳过" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "[星辉] 进程已退出 (PID: $ServerPid)" -ForegroundColor Gray
    }
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
}

# 也尝试停止所有 uvicorn 子进程
Get-Process -Name "python" -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -match "uvicorn" -and $_.CommandLine -match "star_api"
} | Stop-Process -Force -ErrorAction SilentlyContinue