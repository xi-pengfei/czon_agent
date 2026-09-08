[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

function Stop-Install([string]$Message) {
    Write-Host "`n[安装失败] $Message" -ForegroundColor Red
    exit 1
}

Write-Host "`nczon_agent Windows 一键安装" -ForegroundColor Cyan
Write-Host "项目目录：$ProjectRoot`n"

$CurrentIdentity = [Security.Principal.WindowsIdentity]::GetCurrent()
$Principal = New-Object Security.Principal.WindowsPrincipal($CurrentIdentity)
if (-not $Principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Stop-Install "请双击项目根目录的 INSTALL_WINDOWS.cmd，它会自动申请管理员权限。"
}

$Launcher = $null
$LauncherArgs = @()
if (Get-Command py -ErrorAction SilentlyContinue) {
    $Launcher = "py"
    $LauncherArgs = @("-3")
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $Launcher = "python"
} else {
    Stop-Install "没有找到 Python。请先安装 64 位 Python 3.11 或 3.12，并勾选 Add Python to PATH。"
}

Write-Host "[1/5] 检查 Python..."
& $Launcher @LauncherArgs -c "import sys; assert sys.version_info >= (3, 11), '需要 Python 3.11 或更高版本'; print(sys.version)"
if ($LASTEXITCODE -ne 0) {
    Stop-Install "Python 版本不符合要求。"
}

Write-Host "`n[2/5] 创建 Python 环境..."
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    & $Launcher @LauncherArgs -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        Stop-Install "Python 虚拟环境创建失败。"
    }
}
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Stop-Install "Python 虚拟环境创建失败。"
}

Write-Host "`n[3/5] 安装 Python 依赖..."
& $VenvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) {
    Stop-Install "pip 升级失败，请检查网络连接。"
}
& $VenvPython -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    Stop-Install "Python 依赖安装失败，请检查上面的错误信息和网络连接。"
}

Write-Host "`n[4/5] 创建运行目录和管理员..."
@("data", "uploads", "workspace", "logs") | ForEach-Object {
    New-Item -ItemType Directory -Force $_ | Out-Null
}
if (-not (Test-Path ".env")) {
    New-Item -ItemType File ".env" | Out-Null
}
$HasUsers = & $VenvPython -c "import sqlite3; from pathlib import Path; p=Path('data/czon_agent.db'); print(1 if p.exists() and sqlite3.connect(p).execute('SELECT COUNT(*) FROM app_users').fetchone()[0] else 0)" 2>$null
if ($HasUsers -eq "1") {
    Write-Host "检测到现有数据库，跳过管理员创建。"
} else {
    & $VenvPython main.py setup-admin
    if ($LASTEXITCODE -ne 0) {
        Stop-Install "管理员创建失败。"
    }
}

Write-Host "`n[5/5] 创建启动文件..."
$StartFile = Join-Path $ProjectRoot "start_czon_agent.cmd"
$StartContent = @"
@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" main.py webui
pause
"@
Set-Content -Path $StartFile -Value $StartContent -Encoding ASCII

& $VenvPython -c "from main import load_config; load_config(); from adapters.server import create_app; print('程序检查通过')"
if ($LASTEXITCODE -ne 0) {
    Stop-Install "程序检查失败，请检查上面的错误信息。"
}

$FirewallRule = Get-NetFirewallRule -DisplayName "czon_agent WebUI" -ErrorAction SilentlyContinue
if (-not $FirewallRule) {
    New-NetFirewallRule `
        -DisplayName "czon_agent WebUI" `
        -Direction Inbound `
        -Protocol TCP `
        -LocalPort 8000 `
        -Action Allow | Out-Null
}

$PortInUse = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if (-not $PortInUse) {
    Start-Process -FilePath $StartFile
}

Write-Host "`n安装完成。" -ForegroundColor Green
Write-Host "程序已经启动。以后需要手工启动时，双击 $StartFile"
Write-Host "本机地址：http://127.0.0.1:8000"
Write-Host "局域网地址：http://这台电脑的IP:8000"
Write-Host "Windows 防火墙 TCP 8000 端口已经放行。"
Write-Host "首次登录后请立即修改初始密码，并在管理页面配置模型。"
