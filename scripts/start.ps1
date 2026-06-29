<#
.SYNOPSIS
启动群星 Star API 服务
.DESCRIPTION
启动 Uvicorn 服务器，带日志和进程管理功能
#>

param(
    [int]$Port = 8765,
    [string]$Host = "0.0.0.0",
    [switch]$Daemon = $false,
    [switch]$Reload = $false
)

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$LogDir = Join-Path $ProjectRoot "logs"
$PidFile = Join-Path $LogDir "star.pid"
$LogFile = Join-Path $LogDir "star.log"

# 确保日志目录存在
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }

# 检查是否已经在运行
if (Test-Path $PidFile) {
    $OldPid = Get-Content $PidFile -Raw -ErrorAction SilentlyContinue
    if ($OldPid) {
        $OldPid = $OldPid.Trim()
        $Running = Get-Process -Id $OldPid -ErrorAction SilentlyContinue
        if ($Running -and $Running.ProcessName -eq "python") {
            Write-Host "[星辉] 服务已在运行中 (PID: $OldPid)" -ForegroundColor Yellow
            exit 1
        }
    }
}

$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    Write-Host "[错误] 未找到 Python 虚拟环境: $PythonExe" -ForegroundColor Red
    Write-Host "[提示] 请先创建虚拟环境: python -m venv .venv" -ForegroundColor Yellow
    exit 1
}

Write-Host "[星辉] 启动星光接口..." -ForegroundColor Cyan
Write-Host "[星辉] 地址: http://$Host`:$Port" -ForegroundColor Green

if ($Daemon) {
    # 后台模式 - 使用 Start-Process 并写入 PID
    $Args = @(
        "-m", "uvicorn", "star_api.main:app",
        "--host", $Host, "--port", $Port,
        "--log-level", "info"
    )
    if ($Reload) { $Args += "--reload" }

    $Process = Start-Process -FilePath $PythonExe -ArgumentList $Args -NoNewWindow -PassThru -RedirectStandardOutput $LogFile -RedirectStandardError "${LogFile}.err"
    $Process.Id | Out-File -FilePath $PidFile -Force
    Write-Host "[星辉] 服务已启动 (PID: $($Process.Id))" -ForegroundColor Green
    Write-Host "[星辉] 日志文件: $LogFile" -ForegroundColor Gray
} else {
    # 前台模式
    Get-Date -Format "yyyy-MM-dd HH:mm:ss" | Out-File -FilePath $LogFile -Encoding utf8
    & $PythonExe -m uvicorn star_api.main:app --host $Host --port $Port --log-level info 2>&1 | Tee-Object -FilePath $LogFile -Append
}