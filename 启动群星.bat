@echo off
chcp 65001 >nul
setlocal

rem 群星 Star 一键启动（双击即可）
rem 前台运行，关闭本窗口即停止服务。

cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start.ps1"

echo.
echo [星辉] 服务已退出。按任意键关闭窗口。
pause >nul
