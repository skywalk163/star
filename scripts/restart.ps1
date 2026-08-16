<#
.SYNOPSIS
重启群星 Star API 服务
#>

param(
    [int]$Port = 8765,
    [switch]$Daemon = $true
)

& "$PSScriptRoot\stop.ps1"
Start-Sleep -Seconds 2
& "$PSScriptRoot\start.ps1" -Port $Port -Daemon:$Daemon