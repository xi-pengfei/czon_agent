# Ubuntu 手工部署指南

适用于 Ubuntu 22.04、24.04 及之后版本。本文以手工安装为主，每一步都可以单独检查，适合首次部署和故障排查。

## 一键安装入口

如果不需要逐步安装：从 GitHub 下载 ZIP 并解压，在解压目录打开终端，执行：

```bash
bash INSTALL_UBUNTU.sh
```

安装过程需要输入 Ubuntu 账号的 `sudo` 密码，并创建第一个系统管理员。Ubuntu Server 通常没有图形桌面，因此不要依赖双击脚本。一键安装失败时，再按照下文手工处理。

## 部署前准备

需要准备：

- 一台能够被企业内网访问的 Ubuntu 服务器。
- 一个拥有 `sudo` 权限的 Ubuntu 账号。
- 服务器的固定局域网 IP，例如 `192.168.1.20`。
- 能够访问所选模型服务；Ollama 等私有模型也可以位于企业内网。

GitHub 公共仓库不包含客户私有 Skills、业务凭据、模型密钥和运行数据。这些内容需要在基础程序安装后单独交付。

## 第一步：获取源码

以下两种方式任选一种。

### 方式 A：下载 ZIP

1. 在 GitHub 项目页面点击 `Code` → `Download ZIP`。
2. 把 ZIP 上传到 Ubuntu 当前账号的主目录。
3. 执行：

```bash
sudo apt update
sudo apt install -y unzip
unzip czon_agent-main.zip
cd czon_agent-main
```

如果文件名不同，请改成实际 ZIP 文件名。

### 方式 B：使用 Git

```bash
sudo apt update
sudo apt install -y git
git clone https://github.com/xi-pengfei/czon_agent.git
cd czon_agent
```

## 第二步：安装 Python

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
```

检查版本：

```bash
python3 --version
```

建议使用 Python 3.11 或更高版本。

## 第三步：创建运行账号和目录

```bash
sudo useradd --system --create-home --shell /usr/sbin/nologin czon_agent || true
sudo mkdir -p /opt/czon_agent
sudo cp -a . /opt/czon_agent/
sudo chown -R czon_agent:czon_agent /opt/czon_agent
cd /opt/czon_agent
```

`czon_agent` 是专门运行程序的 Ubuntu 系统账号，不是网页登录账号。

## 第四步：安装 Python 依赖

```bash
sudo -u czon_agent python3 -m venv /opt/czon_agent/.venv
sudo -u czon_agent /opt/czon_agent/.venv/bin/python -m pip install --upgrade pip
sudo -u czon_agent /opt/czon_agent/.venv/bin/python -m pip install -r /opt/czon_agent/requirements.txt
```

生产服务器不需要安装 Node.js。已经编译好的前端位于 `webui/`。

## 第五步：创建运行目录

```bash
sudo mkdir -p /opt/czon_agent/data /opt/czon_agent/uploads /opt/czon_agent/workspace /opt/czon_agent/logs
sudo touch /opt/czon_agent/.env
sudo chown -R czon_agent:czon_agent /opt/czon_agent
sudo chmod 600 /opt/czon_agent/.env
```

`.env` 只用于客户私有 Skill 的金蝶、PledgeBox 等业务凭据。模型 API Key 不写入 `.env`，应在网页管理页面配置。

## 第六步：创建第一个管理员

```bash
cd /opt/czon_agent
sudo -u czon_agent /opt/czon_agent/.venv/bin/python main.py setup-admin
```

根据提示输入管理员账号和至少 6 位的初始密码。这是 `czon_agent` 网页系统管理员，首次登录后必须修改初始密码。

## 第七步：注册后台服务

```bash
sudo cp /opt/czon_agent/deploy/systemd/czon_agent.service /etc/systemd/system/czon_agent.service
sudo systemctl daemon-reload
sudo systemctl enable --now czon_agent
sudo systemctl status czon_agent --no-pager
```

看到 `active (running)` 表示程序已经启动，并且以后会随 Ubuntu 自动启动。

## 第八步：选择访问方式

### 方式 A：不用 Nginx

适用于可信局域网、暂时不需要 HTTPS，并且可以接受地址带 `:8000` 的情况。

```text
http://服务器IP:8000
```

如果启用了 UFW：

```bash
sudo ufw allow 8000/tcp
```

### 方式 B：使用 Nginx

Nginx 不是必需组件。它用于标准 `80/443` 端口、HTTPS、访问日志和稳定转发流式输出。

```bash
sudo apt update
sudo apt install -y nginx
sudo cp /opt/czon_agent/deploy/nginx/czon_agent.conf /etc/nginx/sites-available/czon_agent
sudo ln -sf /etc/nginx/sites-available/czon_agent /etc/nginx/sites-enabled/czon_agent
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl enable --now nginx
sudo systemctl reload nginx
```

然后访问 `http://服务器IP`。Nginx 不提供 Basic Auth，不会出现两次登录；用户、角色和权限全部由 `czon_agent` 管理。

如果启用了 UFW：

```bash
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
```

不要执行 `sudo ufw enable`，除非已经确认 SSH 端口不会被拦截。正式生产启用全站 HTTPS 后，把 `config.yaml` 中的 `cookie_secure` 改为 `true`，再重启服务。

## 第九步：完成网页配置

管理员登录后配置模型、组织部门、角色、用户和权限。客户私有 Skills 单独放入 `/opt/czon_agent/skills/`；其业务凭据填写在 `/opt/czon_agent/.env`。

## 日常维护

```bash
# 查看状态
sudo systemctl status czon_agent --no-pager

# 重启程序
sudo systemctl restart czon_agent

# 查看实时日志
sudo journalctl -u czon_agent -f

# 检查并重载 Nginx
sudo nginx -t && sudo systemctl reload nginx
```

## 常见问题

- 网页打不开：检查服务器 IP、服务状态和防火墙端口。
- 出现 `502 Bad Gateway`：检查 `sudo systemctl status czon_agent --no-pager`。
- 其他电脑无法访问：确认 `config.yaml` 中 `webui.host` 为 `0.0.0.0`。
- 模型不可用：管理员进入“模型配置”，重新执行连接测试。
- 修改配置后未生效：执行 `sudo systemctl restart czon_agent`。

## 必须备份的数据

```text
/opt/czon_agent/data/czon_agent.db
/opt/czon_agent/data/czon_agent.key
/opt/czon_agent/data/artifacts/
/opt/czon_agent/.env
/opt/czon_agent/skills/ 中单独交付的客户私有 Skills
```

`czon_agent.db` 和 `czon_agent.key` 必须配套保存。丢失 Key 后，数据库中加密保存的模型密钥无法恢复。
