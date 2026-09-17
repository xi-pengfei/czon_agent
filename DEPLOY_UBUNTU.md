# Ubuntu 部署指南

适用于 Ubuntu 22.04、24.04。程序目录为 `~/czon_agent`，网页端口为 `8000`。

## 1. 下载 czon_agent

以下方式任选一种。

### 下载 ZIP

一般是在自己的 Windows 或 macOS 电脑上打开 GitHub，点击 `Code` → `Download ZIP`。下载完成后，将 ZIP 上传到 Ubuntu 服务器。

假设 Ubuntu 用户名是 `ubuntu`，服务器 IP 是 `192.168.1.100`。请按实际情况替换用户名和 IP。

Windows 打开 PowerShell，执行：

```powershell
scp "$env:USERPROFILE\Downloads\czon_agent-main.zip" ubuntu@192.168.1.100:~/
```

macOS 打开“终端”，执行：

```bash
scp ~/Downloads/czon_agent-main.zip ubuntu@192.168.1.100:~/
```

命令要求输入密码时，输入 Ubuntu 用户的登录密码。输入密码时屏幕不会显示字符，这是正常现象。

上传完成后，登录 Ubuntu 服务器并执行：

```bash
cd ~
sudo apt update && sudo apt install -y unzip
unzip czon_agent-main.zip
mv czon_agent-main czon_agent
cd ~/czon_agent
```

如果 ZIP 文件名或下载位置不同，把命令中的文件名和路径换成实际内容。Windows 提示找不到 `scp` 时，需要先在“可选功能”中安装 OpenSSH 客户端；也可以使用 WinSCP 将 ZIP 拖到 Ubuntu 用户主目录。

### 使用 Git

```bash
cd ~
sudo apt update && sudo apt install -y git
git clone https://github.com/xi-pengfei/czon_agent.git ~/czon_agent
cd ~/czon_agent
```

## 2. 安装 Python 及依赖

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
cd ~/czon_agent
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

## 3. 注册开机启动服务

```bash
mkdir -p ~/.config/systemd/user
cp ~/czon_agent/deploy/systemd/czon_agent.service ~/.config/systemd/user/czon_agent.service
sudo loginctl enable-linger "$USER"
systemctl --user daemon-reload
systemctl --user enable --now czon_agent.service
```

这里仅 `loginctl` 使用 `sudo`，不要执行 `sudo systemctl --user ...`，否则会操作错误用户的服务。

确认开机启动已经启用：

```bash
systemctl --user is-enabled czon_agent.service
loginctl show-user "$USER" -p Linger
```

应分别显示 `enabled` 和 `Linger=yes`。

## 4. 启动 WebUI

上一步已经启动 WebUI。执行以下命令检查状态：

```bash
systemctl --user status czon_agent.service --no-pager
```

看到 `active (running)` 表示启动成功。

查看服务器 IP：

```bash
hostname -I
```

在同一局域网的电脑浏览器中打开：

```text
http://服务器IP:8000
```

首次打开网页时，使用管理员账号 `admin` 设置密码。页面要求安装码时，在服务器执行：

```bash
cd ~/czon_agent
.venv/bin/python main.py setup-code
```

服务器启用了 UFW 时，放行端口：

```bash
sudo ufw allow 8000/tcp
```

## 常用命令

```bash
# 查看状态
systemctl --user status czon_agent.service --no-pager

# 重启
systemctl --user restart czon_agent.service

# 停止
systemctl --user stop czon_agent.service

# 查看最近日志
journalctl --user -u czon_agent.service -n 100 --no-pager
```

如果重启 Ubuntu 后没有自动启动，使用同一个 Ubuntu 用户登录并执行：

```bash
systemctl --user is-enabled czon_agent.service
loginctl show-user "$USER" -p Linger
journalctl --user -b -u czon_agent.service --no-pager
```

第一项不是 `enabled` 时，重新执行 `systemctl --user enable --now czon_agent.service`；第二项不是 `Linger=yes` 时，重新执行 `sudo loginctl enable-linger "$USER"`。最后一条会显示本次开机启动失败的具体原因。

生产环境统一通过 `systemctl --user` 管理，不要直接运行 `.venv/bin/python main.py`。

## 需要备份的内容

```text
~/czon_agent/data/
~/czon_agent/.env
~/czon_agent/skills/ 中后来安装的企业私有 Skills
```
