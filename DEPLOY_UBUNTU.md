# Ubuntu 部署指南

适用于 Ubuntu 22.04、24.04。程序目录为 `~/czon_agent`，网页端口为 `8000`。

## 1. 下载 czon_agent

以下方式任选一种。

### 下载 ZIP

从 GitHub 点击 `Code` → `Download ZIP`，把 ZIP 放到 Ubuntu 用户主目录，然后执行：

```bash
cd ~
sudo apt update && sudo apt install -y unzip
unzip czon_agent-main.zip
mv czon_agent-main czon_agent
cd ~/czon_agent
```

如果 ZIP 文件名不同，把命令中的文件名换成实际名称。

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
systemctl --user enable czon_agent
```

## 4. 启动 WebUI

```bash
systemctl --user start czon_agent
systemctl --user status czon_agent --no-pager
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
systemctl --user status czon_agent --no-pager

# 重启
systemctl --user restart czon_agent

# 停止
systemctl --user stop czon_agent

# 查看最近日志
journalctl --user -u czon_agent -n 100 --no-pager
```

生产环境统一通过 `systemctl --user` 管理，不要直接运行 `.venv/bin/python main.py`。

## 需要备份的内容

```text
~/czon_agent/data/
~/czon_agent/.env
~/czon_agent/skills/ 中后来安装的企业私有 Skills
```
