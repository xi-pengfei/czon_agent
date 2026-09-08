# Ubuntu 部署

`czon_agent` 可以直接运行，Nginx 是可选的反向代理和 HTTPS 入口。直接运行时只使用应用登录；启用随附 Nginx 模板时，Basic Auth 是入口保护，应用账号继续负责角色、会话和数据权限。

## 1. 安装与初始化

```bash
sudo apt update
sudo apt install -y python3 python3-venv
sudo useradd --system --create-home --shell /usr/sbin/nologin czon_agent
sudo mkdir -p /opt/czon_agent
sudo chown -R czon_agent:czon_agent /opt/czon_agent
cd /opt/czon_agent
sudo -u czon_agent python3 -m venv .venv
sudo -u czon_agent .venv/bin/pip install -r requirements.txt
sudo -u czon_agent touch .env
sudo chmod 600 .env
sudo -u czon_agent .venv/bin/python main.py setup-admin
```

`setup-admin` 创建第一个管理员，初始密码不会写入代码或配置文件，首次登录必须修改。
`.env` 不保存模型密钥；只有单独部署的企业私有 Skill 需要业务系统凭据时才填写。

## 2. 注册后台服务

```bash
sudo cp deploy/systemd/czon_agent.service /etc/systemd/system/czon_agent.service
sudo systemctl daemon-reload
sudo systemctl enable --now czon_agent
sudo systemctl status czon_agent
```

## 3. 方式一：直接访问

`config.yaml` 保持：

```yaml
webui:
  host: 0.0.0.0
  port: 8000
  cookie_secure: false
```

只允许客户真实内网网段访问，例如：

```bash
sudo ufw allow from 192.168.1.0/24 to any port 8000 proto tcp
```

用户访问 `http://服务器IP:8000`，登录、管理和对话功能完整可用。

## 4. 方式二：可选 Nginx

```bash
sudo apt install -y nginx apache2-utils libnginx-mod-http-headers-more-filter
sudo htpasswd -c /etc/nginx/czon_agent.htpasswd gateway_admin
sudo cp deploy/nginx/czon_agent.conf /etc/nginx/sites-available/czon_agent
sudo ln -s /etc/nginx/sites-available/czon_agent /etc/nginx/sites-enabled/czon_agent
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx
```

执行 `htpasswd` 后输入的是 Nginx 入口账号密码，密码以哈希形式保存在 `/etc/nginx/czon_agent.htpasswd`。用户访问 `http://服务器IP` 时先看到浏览器的 Basic Auth 提示，通过后再进入 `czon_agent` 登录页。前者保护整个入口，后者区分企业用户及权限，两者用途不同。

不需要双层入口保护时，可以删除 Nginx 配置里的 `auth_basic` 和 `auth_basic_user_file` 两行，应用登录仍然完整可用。

使用 Nginx 时建议不要对外放行 8000，只放行 80/443。应用仍可监听 `0.0.0.0:8000`，Nginx 从本机的 `127.0.0.1:8000` 转发，程序行为不会变化。

正式生产建议由客户内部 CA 提供证书，在 Nginx 配置 HTTPS，并把 `config.yaml` 的 `cookie_secure` 改为 `true` 后重启应用。普通 HTTP 无法保护密码和业务内容。

## 5. 日常管理

```bash
sudo systemctl restart czon_agent
sudo systemctl status czon_agent
sudo journalctl -u czon_agent -f
sudo nginx -t && sudo systemctl reload nginx
```

管理员登录后可以管理组织架构、用户、角色、Skills 权限、工具权限、模型和日志。模型 API Key 统一在模型页面填写并加密保存在数据库中。

备份数据前短暂停止服务：

```bash
sudo systemctl stop czon_agent
sudo cp /opt/czon_agent/data/czon_agent.db /opt/czon_agent/data/czon_agent.db.backup
sudo cp /opt/czon_agent/data/czon_agent.key /opt/czon_agent/data/czon_agent.key.backup
sudo cp -a /opt/czon_agent/data/artifacts /opt/czon_agent/data/artifacts.backup
sudo systemctl start czon_agent
```

数据库和 `czon_agent.key` 必须一起备份并限制读取权限。生产运行不需要 Node.js；只有在服务器上修改 React 源码并重新生成 `webui/` 时才需要安装 Node.js 并执行 `cd frontend && npm ci && npm run build`。

## 6. 故障定位

- `502 Bad Gateway`：检查 `sudo systemctl status czon_agent`。
- 登录失败：确认账号未被管理员禁用；第一个管理员使用 `setup-admin` 创建。
- Nginx 页面回复中断：确认配置中保留 `proxy_buffering off` 和 `proxy_read_timeout 16m`。
- 局域网无法直连：检查服务器 IP、UFW、端口 8000 和现场网络策略。
