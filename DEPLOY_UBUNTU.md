# Ubuntu 部署指南

适用于 Ubuntu 22.04、24.04 及之后版本。推荐使用“一键安装”；手工安装仅用于需要逐步检查的现场。

## 部署前准备

你需要：

- 一台能够被企业内网访问的 Ubuntu 电脑或服务器。
- 一个拥有 `sudo` 权限的 Ubuntu 账号。
- 服务器的固定局域网 IP，例如 `192.168.1.20`。
- 能够访问模型服务；使用 Ollama 时也可以连接企业内网模型。

GitHub 公共仓库不包含客户私有 Skills、业务凭据、模型密钥和运行数据。这些内容需要在基础程序安装完成后单独放入客户服务器。

## 方法一：一键安装（推荐）

### 第一步：获取程序，二选一

#### A. 从 GitHub 网页下载

1. 打开项目 GitHub 页面。
2. 点击 `Code`，再点击 `Download ZIP`。
3. 把 ZIP 文件上传到 Ubuntu，例如上传到当前账号的主目录。
4. 执行：

```bash
sudo apt update
sudo apt install -y unzip
unzip czon_agent-main.zip
cd czon_agent-main
```

ZIP 文件名如果不同，请把命令中的名称改成实际文件名。

#### B. 使用 Git 命令下载

```bash
sudo apt update
sudo apt install -y git
git clone https://github.com/xi-pengfei/czon_agent.git
cd czon_agent
```

### 第二步：运行一键安装脚本

```bash
sudo bash deploy/install_ubuntu.sh
```

脚本会自动完成：

1. 安装 Python 和必要组件。
2. 把程序安装到 `/opt/czon_agent`。
3. 创建独立的 `czon_agent` 系统账号。
4. 安装 Python 依赖。
5. 创建第一个系统管理员。
6. 注册开机自动运行的后台服务。
7. 根据你的选择安装并配置 Nginx。
8. 启动程序并检查运行状态。

创建管理员时需要输入账号和至少 6 位的初始密码。首次登录后，系统会要求修改密码。

### 第三步：打开网页

- 安装 Nginx：访问 `http://服务器IP`
- 不安装 Nginx：访问 `http://服务器IP:8000`

例如服务器 IP 是 `192.168.1.20`：

```text
http://192.168.1.20
```

或者：

```text
http://192.168.1.20:8000
```

这里仅使用 `czon_agent` 自己的登录页面，不再增加 Nginx Basic Auth，不会出现两次登录。

### 第四步：完成系统配置

管理员登录后依次完成：

1. 在“模型配置”中添加模型和 API Key，并执行连接测试。
2. 创建组织部门。
3. 创建角色并选择允许使用的 Skills、工具和模型。
4. 创建用户并分配部门和角色。
5. 安全交付客户私有 Skills，并放入 `/opt/czon_agent/skills/`。
6. 私有 Skill 如需金蝶、PledgeBox 等凭据，将其写入 `/opt/czon_agent/.env`。

模型 API Key 只在管理页面配置，不要写入 `.env`。

## Nginx 要不要安装

Nginx 不是程序运行的必需组件。

不使用 Nginx 适合：

- 仅在可信局域网内使用。
- 可以接受地址中带有 `:8000`。
- 暂时不配置 HTTPS。

使用 Nginx 适合：

- 希望直接使用 `http://服务器IP`，不显示端口号。
- 需要配置 HTTPS。
- 希望统一控制上传大小、访问日志和连接超时。
- 后续可能在同一台服务器部署多个系统。

本项目的 Nginx 只负责反向代理，不再提供第二套账号密码。用户、角色、权限和会话仍全部由 `czon_agent` 管理。

## 方法二：手工安装

获取源码并进入源码目录后执行：

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
sudo useradd --system --create-home --shell /usr/sbin/nologin czon_agent || true
sudo mkdir -p /opt/czon_agent
sudo cp -a . /opt/czon_agent/
sudo chown -R czon_agent:czon_agent /opt/czon_agent
sudo -u czon_agent python3 -m venv /opt/czon_agent/.venv
sudo -u czon_agent /opt/czon_agent/.venv/bin/pip install -r /opt/czon_agent/requirements.txt
sudo -u czon_agent touch /opt/czon_agent/.env
sudo chmod 600 /opt/czon_agent/.env
sudo -u czon_agent /opt/czon_agent/.venv/bin/python /opt/czon_agent/main.py setup-admin
```

注册后台服务：

```bash
sudo cp /opt/czon_agent/deploy/systemd/czon_agent.service /etc/systemd/system/czon_agent.service
sudo systemctl daemon-reload
sudo systemctl enable --now czon_agent
sudo systemctl status czon_agent --no-pager
```

如果需要 Nginx：

```bash
sudo apt install -y nginx
sudo cp /opt/czon_agent/deploy/nginx/czon_agent.conf /etc/nginx/sites-available/czon_agent
sudo ln -sf /etc/nginx/sites-available/czon_agent /etc/nginx/sites-enabled/czon_agent
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl enable --now nginx
sudo systemctl reload nginx
```

## 防火墙

如果服务器启用了 UFW，请根据部署方式选择一组命令。

使用 Nginx：

```bash
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
```

不使用 Nginx：

```bash
sudo ufw allow 8000/tcp
```

企业现场有独立防火墙时，还需要由网络管理员放行对应端口。不要执行 `sudo ufw enable`，除非已经确认 SSH 端口不会被拦截。

## 日常命令

查看运行状态：

```bash
sudo systemctl status czon_agent --no-pager
```

重启程序：

```bash
sudo systemctl restart czon_agent
```

查看实时日志：

```bash
sudo journalctl -u czon_agent -f
```

检查并重载 Nginx：

```bash
sudo nginx -t && sudo systemctl reload nginx
```

## 常见问题

- 网页打不开：检查服务器 IP、服务状态和防火墙端口。
- 出现 `502 Bad Gateway`：执行 `sudo systemctl status czon_agent --no-pager`。
- 模型不可用：管理员进入“模型配置”，重新测试模型连接。
- 其他电脑不能访问：确认 `config.yaml` 中 `webui.host` 是 `0.0.0.0`。
- 修改配置后没有生效：执行 `sudo systemctl restart czon_agent`。

## 必须备份的数据

以下内容必须一起备份：

```text
/opt/czon_agent/data/czon_agent.db
/opt/czon_agent/data/czon_agent.key
/opt/czon_agent/data/artifacts/
/opt/czon_agent/.env
/opt/czon_agent/skills/ 中单独交付的客户私有 Skills
```

`czon_agent.db` 和 `czon_agent.key` 必须配套保存。丢失 Key 后，数据库中加密保存的模型密钥无法恢复。
