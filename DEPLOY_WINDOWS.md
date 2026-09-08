# Windows 手工部署指南

适用于 Windows 10、Windows 11 和 Windows Server。本文以手工安装为主，每一步都可以单独检查，适合首次部署和故障排查。

Windows 默认直接运行 `czon_agent`，不安装 Nginx。Nginx 官方仍把 Windows 版本视为测试版本，并且它默认不是 Windows 服务，因此正式生产更推荐 Ubuntu。

## 一键安装入口

如果不需要逐步安装：从 GitHub 下载 ZIP，解压到固定目录，推荐 `C:\czon_agent`，然后双击根目录的：

```text
INSTALL_WINDOWS.cmd
```

Windows 询问是否允许更改设备时点击“是”。安装程序会自动申请管理员权限、安装 Python 依赖、放行 TCP `8000` 端口并启动程序。一键安装失败时，再按照下文手工处理。

## 部署前准备

需要准备：

- 64 位 Python 3.11 或 3.12，安装时勾选“Add Python to PATH”。
- 如果使用 Git 命令下载，安装 Git for Windows。
- 为这台 Windows 电脑配置固定局域网 IP。
- 确保能够访问所选模型服务。

GitHub 公共仓库不包含客户私有 Skills、业务凭据、模型密钥和运行数据。这些内容需要在基础程序安装后单独交付。

## 第一步：获取源码

以下两种方式任选一种。

### 方式 A：下载 ZIP

1. 在 GitHub 项目页面点击 `Code` → `Download ZIP`。
2. 解压到固定位置，推荐 `C:\czon_agent`。
3. 打开解压后的项目文件夹。
4. 在文件夹空白处按住 `Shift` 并点击鼠标右键，选择“在终端中打开”。

ZIP 经常会多一层 `czon_agent-main` 目录。请确认当前目录中能直接看到 `main.py` 和 `requirements.txt`。

### 方式 B：使用 Git

```powershell
cd C:\
git clone https://github.com/xi-pengfei/czon_agent.git
cd C:\czon_agent
```

## 第二步：检查 Python

```powershell
py -3 --version
```

应显示 Python 3.11 或更高版本。如果提示找不到 `py`，尝试 `python --version`；两个命令都找不到时，重新安装 Python 并勾选加入 PATH。

## 第三步：创建 Python 环境

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

如果电脑只有 `python` 命令，把第一行的 `py -3` 换成 `python`。生产运行不需要 Node.js，已编译前端位于 `webui` 文件夹。

## 第四步：创建运行目录

```powershell
New-Item -ItemType Directory -Force data, uploads, workspace, logs | Out-Null
New-Item -ItemType File -Force .env | Out-Null
```

`.env` 只用于客户私有 Skill 的业务凭据。模型 API Key 不写入 `.env`，应在网页管理页面配置。

## 第五步：创建第一个管理员

```powershell
.\.venv\Scripts\python.exe main.py setup-admin
```

根据提示输入管理员账号和至少 6 位的初始密码。这是 `czon_agent` 网页系统管理员，首次登录后必须修改初始密码。

## 第六步：启动程序

```powershell
.\.venv\Scripts\python.exe main.py webui
```

命令窗口不能关闭。关闭窗口或按 `Ctrl+C` 会停止程序。

一键安装会自动生成 `start_czon_agent.cmd`。手工安装也可以在项目根目录新建同名文件：

```bat
@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" main.py webui
pause
```

以后双击 `start_czon_agent.cmd` 即可启动。

## 第七步：开放 Windows 防火墙

只有局域网其他电脑需要访问时才执行。以管理员身份打开 PowerShell：

```powershell
New-NetFirewallRule `
  -DisplayName "czon_agent WebUI" `
  -Direction Inbound `
  -Protocol TCP `
  -LocalPort 8000 `
  -Action Allow
```

如果客户不允许执行，请让网络管理员放行 TCP `8000` 端口。

## 第八步：打开网页

服务器本机访问 `http://127.0.0.1:8000`。执行 `ipconfig` 找到当前网卡的 IPv4 地址，局域网其他用户访问 `http://Windows电脑IP:8000`。

## 第九步：完成网页配置

管理员登录后配置模型、组织部门、角色、用户和权限。客户私有 Skills 单独放入项目的 `skills` 文件夹；其业务凭据填写在项目根目录的 `.env`。

## 开机自动启动

1. 按 `Win + R`。
2. 输入 `shell:startup` 并回车。
3. 为 `start_czon_agent.cmd` 创建快捷方式。
4. 把快捷方式放进打开的启动文件夹。

这种方式需要用户登录 Windows 后才会启动。Windows Server 如需无人登录时持续运行，建议使用 Ubuntu 虚拟机，或由运维人员把 Python 进程注册为正式 Windows 服务。

## 日常维护

- 启动：双击 `start_czon_agent.cmd`。
- 停止：在运行窗口按 `Ctrl+C`。
- 重启：停止后重新双击启动文件。
- 日志：查看项目的 `logs` 文件夹和运行窗口。

## 常见问题

- 找不到 `py` 或 `python`：重新安装 Python 并勾选加入 PATH。
- PowerShell 禁止运行脚本：执行 `Set-ExecutionPolicy -Scope Process Bypass`。
- 其他电脑打不开：检查 Windows IP、防火墙和客户网络策略。
- 模型不可用：管理员进入“模型配置”，重新执行连接测试。
- 修改配置后未生效：停止程序后重新启动。

## 必须备份的数据

```text
data\czon_agent.db
data\czon_agent.key
data\artifacts\
.env
skills\ 中单独交付的客户私有 Skills
```

`czon_agent.db` 和 `czon_agent.key` 必须配套保存。丢失 Key 后，数据库中加密保存的模型密钥无法恢复。
