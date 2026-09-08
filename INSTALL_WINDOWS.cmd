@echo off
chcp 65001 >nul
cd /d "%~dp0"

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo 正在请求管理员权限...
    powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

echo czon_agent Windows 安装程序
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy\install_windows.ps1"
if %errorlevel% neq 0 (
    echo.
    echo 安装失败，请查看上面的错误信息。
) else (
    echo.
    echo 安装完成。
)
echo.
pause
