[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$DownloadUrl = "https://github.com/xi-pengfei/czon_agent/archive/refs/heads/main.zip"
$InstallDir = "C:\czon_agent"
$TempDir = Join-Path $env:TEMP ("czon_agent_install_" + [Guid]::NewGuid().ToString("N"))
$Archive = Join-Path $TempDir "czon_agent.zip"

function Stop-Download([string]$Message) {
    Write-Host "`n[下载失败] $Message" -ForegroundColor Red
    exit 1
}

$CurrentIdentity = [Security.Principal.WindowsIdentity]::GetCurrent()
$Principal = New-Object Security.Principal.WindowsPrincipal($CurrentIdentity)
if (-not $Principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Stop-Download "请右键 PowerShell，选择“以管理员身份运行”，然后重新执行安装命令。"
}

[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

if (Test-Path $InstallDir) {
    $Existing = Get-ChildItem -Force $InstallDir -ErrorAction SilentlyContinue
    if ($Existing) {
        Stop-Download "$InstallDir 已存在。为避免覆盖客户数据，在线安装已停止。"
    }
    Remove-Item -Force $InstallDir
}

Write-Host "`nczon_agent Windows 在线安装" -ForegroundColor Cyan
Write-Host "正在从 GitHub 下载最新版..."

try {
    New-Item -ItemType Directory -Force $TempDir | Out-Null
    Invoke-WebRequest -UseBasicParsing -Uri $DownloadUrl -OutFile $Archive
    Expand-Archive -Path $Archive -DestinationPath $TempDir -Force

    $SourceDir = Join-Path $TempDir "czon_agent-main"
    $Installer = Join-Path $SourceDir "deploy\install_windows.ps1"
    if (-not (Test-Path $Installer)) {
        Stop-Download "下载内容不完整，请检查网络后重试。"
    }

    Move-Item -Path $SourceDir -Destination $InstallDir
    & (Join-Path $InstallDir "deploy\install_windows.ps1")
} catch {
    Stop-Download $_.Exception.Message
} finally {
    if (Test-Path $TempDir) {
        Remove-Item -Recurse -Force $TempDir
    }
}
