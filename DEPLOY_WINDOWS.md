# Windows 部署指南

适用于 Windows 10、Windows 11 和 Windows Server。Windows 默认直接运行 `czon_agent`，不安装 Nginx，也不会出现双重登录。

正式生产更推荐 Ubuntu。Nginx 官方仍把 Windows 版本视为测试版本，并且它默认不是 Windows 服务，因此本项目不把 Windows Nginx 作为标准部署方式。

## 部署前准备

1. 安装 64 位 Python 3.11 或 3.12，安装时勾选“Add Python to PATH”。
2. 如果要通过命令下载，再安装 Git for Windows。
3. 确认客户电脑在企业局域网内有固定 IP。

GitHub 公共仓库不包含客户私有 Skills、业务凭据、模型密钥和运行数据。这些内容需要在基础程序安装完成后单独交付。

## 方法一：联网一键安装（推荐）

在开始菜单搜索 PowerShell，点击右键，选择“以管理员身份运行”，然后执行：

```powershell
$installer = "$env:TEMP\czon_agent_bootstrap.ps1"
Invoke-WebRequest https://raw.githubusercontent.com/xi-pengfei/czon_agent/main/deploy/bootstrap_windows.ps1 -OutFile $installer
powershell -ExecutionPolicy Bypass -File $installer
```

脚本会自动从 GitHub 下载最新版到 `C:\czon_agent`，然后创建 Python 环境、安装依赖并创建系统管理员。

如果 `C:\czon_agent` 已经存在，脚本会立即停止，不会覆盖数据库、配置或客户私有 Skills。

## 方法二：先获取源码，再一键安装

### 第一步：获取程序，二选一

#### A. 从 GitHub 网页下载

1. 打开项目 GitHub 页面。
2. 点击 `Code`，再点击 `Download ZIP`。
3. 解压 ZIP，例如解压到 `C:\czon_agent`。
4. 打开解压后的项目文件夹。
5. 在文件夹空白处按住 `Shift` 并点击鼠标右键，选择“在终端中打开”。

#### B. 使用 Git 命令下载

打开 PowerShell，执行：

```powershell
cd C:\
git clone https://github.com/xi-pengfei/czon_agent.git
cd C:\czon_agent
```

### 第二步：运行安装脚本

在项目目录的 PowerShell 中执行：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\deploy\install_windows.ps1
```

脚本会自动完成：

1. 检查 Python。
2. 创建独立 Python 环境。
3. 安装依赖。
4. 创建数据、上传、工作区和日志目录。
5. 创建第一个系统管理员。
6. 创建 Windows 启动脚本。
7. 检查程序配置和核心模块能否正常载入。

创建管理员时需要输入账号和至少 6 位的初始密码。首次登录后，系统会要求修改密码。

### 第三步：启动程序

双击项目根目录中的：

```text
start_czon_agent.cmd
```

不要关闭弹出的命令窗口。关闭窗口就会停止服务。

也可以在 PowerShell 中启动：

```powershell
.\.venv\Scripts\python.exe main.py webui
```

### 第四步：打开网页

服务器本机访问：

```text
http://127.0.0.1:8000
```

局域网其他电脑访问：

```text
http://Windows电脑的局域网IP:8000
```

查看 Windows IP：

```powershell
ipconfig
```

找到当前网卡的“IPv4 地址”，例如 `192.168.1.30`，其他用户访问：

```text
http://192.168.1.30:8000
```

### 第五步：完成系统配置

管理员登录后依次完成：

1. 在“模型配置”中添加模型和 API Key，并执行连接测试。
2. 创建组织部门。
3. 创建角色并选择允许使用的 Skills、工具和模型。
4. 创建用户并分配部门和角色。
5. 把单独交付的客户私有 Skills 放入项目的 `skills` 文件夹。
6. 私有 Skill 如需业务凭据，将其写入项目根目录的 `.env`。

模型 API Key 只在管理页面配置，不要写入 `.env`。

## 方法三：完全手工安装

获取源码并进入项目目录后，在 PowerShell 中执行：

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
New-Item -ItemType Directory -Force data, uploads, workspace, logs | Out-Null
New-Item -ItemType File -Force .env | Out-Null
.\.venv\Scripts\python.exe main.py setup-admin
.\.venv\Scripts\python.exe main.py webui
```

如果电脑没有 `py` 命令，把以上命令中的 `py -3` 换成 `python`。

## 开放 Windows 防火墙

只有局域网其他电脑需要访问时才执行。以管理员身份打开 PowerShell：

```powershell
New-NetFirewallRule `
  -DisplayName "czon_agent WebUI" `
  -Direction Inbound `
  -Protocol TCP `
  -LocalPort 8000 `
  -Action Allow
```

如果不允许执行该命令，请让客户的网络管理员放行 TCP `8000` 端口。

## 开机自动启动

普通办公电脑可以把 `start_czon_agent.cmd` 的快捷方式放入 Windows 启动文件夹：

1. 按 `Win + R`。
2. 输入 `shell:startup` 并回车。
3. 为 `start_czon_agent.cmd` 创建快捷方式。
4. 把快捷方式放进打开的启动文件夹。

这种方式需要用户登录 Windows 后才会启动。Windows Server 如需在无人登录时持续运行，建议使用 Ubuntu 虚拟机部署，或者由运维人员将 Python 进程注册为正式 Windows 服务。

## 日常操作

- 启动：双击 `start_czon_agent.cmd`。
- 停止：在运行窗口按 `Ctrl+C`。
- 重启：先按 `Ctrl+C`，再重新双击启动文件。
- 日志：查看项目的 `logs` 文件夹和运行窗口。

## 常见问题

- 提示找不到 `py` 或 `python`：重新安装 Python，并勾选加入 PATH。
- PowerShell 禁止运行脚本：先执行 `Set-ExecutionPolicy -Scope Process Bypass`。
- 其他电脑打不开：检查 Windows IP、防火墙和客户网络策略。
- 模型不可用：管理员进入“模型配置”，重新测试模型连接。
- 修改配置后没有生效：停止程序后重新启动。

## 必须备份的数据

以下内容必须一起备份：

```text
data\czon_agent.db
data\czon_agent.key
data\artifacts\
.env
skills\ 中单独交付的客户私有 Skills
```

`czon_agent.db` 和 `czon_agent.key` 必须配套保存。丢失 Key 后，数据库中加密保存的模型密钥无法恢复。
