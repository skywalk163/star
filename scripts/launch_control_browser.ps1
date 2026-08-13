# 启动"群星管控浏览器"：Edge 优先、回退 Chrome，开启 CDP 调试端口 9222
# 用法：powershell -NoProfile -ExecutionPolicy Bypass -File scripts\launch_control_browser.ps1
$ErrorActionPreference = "Stop"

$Port = 9222
$ProfileDir = Join-Path $env:USERPROFILE ".star\browser-profile"

# 1. 确保 profile 目录存在
New-Item -ItemType Directory -Force -Path $ProfileDir | Out-Null

# 2. 若 9222 已被占用且 /json 可达，说明已有管控浏览器在跑，直接复用并退出
try {
    $Resp = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/json" -UseBasicParsing -TimeoutSec 2
    if ($Resp.StatusCode -eq 200) {
        Write-Host "[cdp] 端口 $Port 的 CDP 端点已可达，复用现有管控浏览器实例。"
        exit 0
    }
} catch {
    # 端口未开放，继续走启动流程
}

# 3. 定位浏览器可执行文件：Edge 优先（32/64 位），回退 Chrome
$Candidates = @(
    "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
    "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe"
)
$Browser = $Candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $Browser) {
    Write-Error "[cdp] 未找到 Edge 或 Chrome，请先安装浏览器后再启动管控浏览器。"
    exit 1
}

# 4. 以前台无关方式启动浏览器（独立 user-data-dir，不与日常浏览器冲突）
$LaunchArgs = @(
    "--remote-debugging-port=$Port",
    "--user-data-dir=`"$ProfileDir`"",
    "--no-first-run",
    "--no-default-browser-check"
)
Write-Host "[cdp] 启动管控浏览器: $Browser"
Write-Host "[cdp] profile     : $ProfileDir"
Start-Process -FilePath $Browser -ArgumentList $LaunchArgs
Write-Host "[cdp] 已启动，CDP 端点: http://127.0.0.1:$Port/json"