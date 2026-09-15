[CmdletBinding()]
param(
    [ValidatePattern('^\d+\.\d+\.\d+$')]
    [string]$Version = "1.0.0"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BuildRoot = Join-Path $ProjectRoot ".packaging-build\windows"
$Wheelhouse = Join-Path $BuildRoot "wheelhouse"
$WindowsRequirements = Join-Path $BuildRoot "requirements-windows.txt"
$ReleaseRoot = Join-Path $ProjectRoot "release\windows"
$IssFile = Join-Path $ProjectRoot "packaging\windows\czon_agent.iss"

function Find-InnoCompiler {
    $Candidates = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
    )
    return $Candidates | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
}

if (-not [Environment]::Is64BitOperatingSystem) {
    throw "当前构建脚本仅生成 Windows x64 安装包。"
}

$InnoCompiler = Find-InnoCompiler
if (-not $InnoCompiler) {
    throw "没有找到 Inno Setup 6。请先安装 Inno Setup 6，再重新运行本脚本。"
}

$Python = Get-Command py -ErrorAction SilentlyContinue
if (-not $Python) {
    throw "构建电脑需要安装 Python，并提供 py 命令。"
}

Remove-Item -Recurse -Force $BuildRoot -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $Wheelhouse, $ReleaseRoot | Out-Null

$PythonVersion = "3.12.10"
$PythonInstallerUrl = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-amd64.exe"
$WinSwUrl = "https://github.com/winsw/winsw/releases/download/v2.12.0/WinSW-x64.exe"

Write-Host "[1/4] 下载独立 Python 安装程序..."
Invoke-WebRequest -UseBasicParsing -Uri $PythonInstallerUrl -OutFile (Join-Path $BuildRoot "python-installer.exe")

Write-Host "[2/4] 下载 Windows 服务包装器..."
Invoke-WebRequest -UseBasicParsing -Uri $WinSwUrl -OutFile (Join-Path $BuildRoot "czon_agent_service.exe")

Write-Host "[3/4] 准备离线 Python 依赖..."
$Requirements = Get-Content (Join-Path $ProjectRoot "requirements.txt") | ForEach-Object {
    $_ -replace '^uvicorn\[standard\]', 'uvicorn'
}
$Requirements | Set-Content -Path $WindowsRequirements -Encoding ASCII
& py -3 -m pip download `
    --only-binary=:all: `
    --implementation cp `
    --python-version 312 `
    --abi cp312 `
    --platform win_amd64 `
    --dest $Wheelhouse `
    --requirement $WindowsRequirements
if ($LASTEXITCODE -ne 0) { throw "Python 依赖下载失败。" }

Write-Host "[4/4] 生成 Setup.exe..."
& $InnoCompiler "/DMyAppVersion=$Version" "/O$ReleaseRoot" $IssFile
if ($LASTEXITCODE -ne 0) { throw "Inno Setup 编译失败。" }

$Output = Join-Path $ReleaseRoot "czon_agent_${Version}_windows_x64.exe"
if (-not (Test-Path $Output)) { throw "没有找到生成的安装包：$Output" }
Write-Host "安装包已生成：$Output" -ForegroundColor Green
