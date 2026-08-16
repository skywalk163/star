<#
.SYNOPSIS
启动群星 Star API 服务
.DESCRIPTION
启动 Uvicorn 服务器，带日志和进程管理功能
#>

param(
    [int]$Port = 8765,
    [string]$BindHost = "127.0.0.1",
    [switch]$Daemon = $false,
    [switch]$Reload = $false
)

# $PSScriptRoot 即本脚本所在的 scripts 目录，其父目录才是项目根。
# （曾误用两次 Split-Path 指向了项目上一级，导致找不到 .venv）
$ProjectRoot = Split-Path -Parent $PSScriptRoot
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
    # 没有虚拟环境时退回 PATH 上的 python，让用户不必先建 venv 也能跑起来
    $Fallback = (Get-Command python -ErrorAction SilentlyContinue).Source
    if ($Fallback) {
        Write-Host "[星辉] 未找到 .venv，使用系统 Python: $Fallback" -ForegroundColor Yellow
        $PythonExe = $Fallback
    } else {
        Write-Host "[错误] 未找到 Python。请先安装 Python 3.10+ 并加入 PATH。" -ForegroundColor Red
        Write-Host "[提示] 或在项目根目录建虚拟环境: python -m venv .venv" -ForegroundColor Yellow
        exit 1
    }
}

# 依赖自检：缺包时给出可直接复制的安装命令，而不是让 uvicorn 抛 ImportError
$Probe = & $PythonExe -c "import importlib.util; miss=[m for m in ('yaml','fastapi','uvicorn','psutil','websockets') if importlib.util.find_spec(m) is None]; print(','.join(miss))" 2>&1
if ($LASTEXITCODE -ne 0) { $Probe = "" }
if ($Probe -and $Probe.Trim()) {
    Write-Host "[错误] 缺少依赖: $($Probe.Trim())" -ForegroundColor Red
    Write-Host "[提示] 请执行: $PythonExe -m pip install -r `"$ProjectRoot\requirements.txt`"" -ForegroundColor Yellow
    exit 1
}

Write-Host "[星辉] 启动星光接口..." -ForegroundColor Cyan
Write-Host "[星辉] 控制台: http://${BindHost}:$Port/ui/pages/starmap.html" -ForegroundColor Green

if ($Daemon) {
    # 后台模式 - 使用 Start-Process 并写入 PID
    $Args = @(
        "-m", "uvicorn", "star_api.main:app",
        "--host", $BindHost, "--port", $Port,
        "--log-level", "info"
    )
    if ($Reload) { $Args += "--reload" }

    $Process = Start-Process -FilePath $PythonExe -ArgumentList $Args -WorkingDirectory $ProjectRoot -NoNewWindow -PassThru -RedirectStandardOutput $LogFile -RedirectStandardError "${LogFile}.err"
    $Process.Id | Out-File -FilePath $PidFile -Force
    Write-Host "[星辉] 服务已启动 (PID: $($Process.Id))" -ForegroundColor Green
    Write-Host "[星辉] 日志文件: $LogFile" -ForegroundColor Gray
} else {
    # 前台模式
    Push-Location $ProjectRoot
    try {
        Get-Date -Format "yyyy-MM-dd HH:mm:ss" | Out-File -FilePath $LogFile -Encoding utf8
        & $PythonExe -m uvicorn star_api.main:app --host $BindHost --port $Port --log-level info 2>&1 | Tee-Object -FilePath $LogFile -Append
    } finally {
        Pop-Location
    }
}