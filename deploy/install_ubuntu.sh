#!/usr/bin/env bash
set -Eeuo pipefail

INSTALL_DIR="/opt/czon_agent"
SERVICE_USER="czon_agent"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

fail() {
  printf '\n[安装失败] %s\n' "$1" >&2
  exit 1
}

if [[ "${EUID}" -ne 0 ]]; then
  fail "请使用 sudo bash deploy/install_ubuntu.sh 运行。"
fi

if [[ ! -f /etc/os-release ]]; then
  fail "无法识别操作系统。此脚本仅支持 Ubuntu。"
fi

# shellcheck disable=SC1091
source /etc/os-release
if [[ "${ID:-}" != "ubuntu" ]]; then
  fail "检测到 ${PRETTY_NAME:-未知系统}。此脚本仅支持 Ubuntu。"
fi

printf '\nczon_agent Ubuntu 一键安装\n'
printf '程序将安装到：%s\n\n' "$INSTALL_DIR"

USE_NGINX=""
while [[ "$USE_NGINX" != "y" && "$USE_NGINX" != "n" ]]; do
  read -r -p "是否安装 Nginx？直接按回车表示安装，输入 n 表示不安装 [Y/n]：" USE_NGINX
  USE_NGINX="${USE_NGINX,,}"
  USE_NGINX="${USE_NGINX:-y}"
done

if [[ "$SOURCE_DIR" != "$INSTALL_DIR" && -e "$INSTALL_DIR" ]] && find "$INSTALL_DIR" -mindepth 1 -print -quit | grep -q .; then
  fail "$INSTALL_DIR 已存在且不是空目录。为避免覆盖数据，脚本已停止。"
fi

printf '\n[1/7] 安装系统组件...\n'
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y python3 python3-venv python3-pip rsync curl
if [[ "$USE_NGINX" == "y" ]]; then
  DEBIAN_FRONTEND=noninteractive apt-get install -y nginx
fi

printf '\n[2/7] 创建运行账号和安装目录...\n'
if ! id "$SERVICE_USER" >/dev/null 2>&1; then
  useradd --system --create-home --shell /usr/sbin/nologin "$SERVICE_USER"
fi
mkdir -p "$INSTALL_DIR"

if [[ "$SOURCE_DIR" != "$INSTALL_DIR" ]]; then
  rsync -a \
    --exclude '.git/' \
    --exclude '.venv/' \
    --exclude '.env' \
    --exclude 'data/' \
    --exclude 'uploads/' \
    --exclude 'workspace/' \
    --exclude 'logs/' \
    "$SOURCE_DIR/" "$INSTALL_DIR/"
fi

mkdir -p "$INSTALL_DIR/data" "$INSTALL_DIR/uploads" "$INSTALL_DIR/workspace" "$INSTALL_DIR/logs"
touch "$INSTALL_DIR/.env"
chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"
chmod 600 "$INSTALL_DIR/.env"

printf '\n[3/7] 创建 Python 环境并安装依赖...\n'
if [[ ! -x "$INSTALL_DIR/.venv/bin/python" ]]; then
  runuser -u "$SERVICE_USER" -- python3 -m venv "$INSTALL_DIR/.venv"
fi
runuser -u "$SERVICE_USER" -- "$INSTALL_DIR/.venv/bin/python" -m pip install --upgrade pip
runuser -u "$SERVICE_USER" -- "$INSTALL_DIR/.venv/bin/python" -m pip install -r "$INSTALL_DIR/requirements.txt"

printf '\n[4/7] 创建系统管理员...\n'
HAS_USERS="$(runuser -u "$SERVICE_USER" -- "$INSTALL_DIR/.venv/bin/python" -c \
  "import sqlite3; from pathlib import Path; p=Path('$INSTALL_DIR/data/czon_agent.db'); print(1 if p.exists() and sqlite3.connect(p).execute('SELECT COUNT(*) FROM app_users').fetchone()[0] else 0)" \
  2>/dev/null || printf '0')"
if [[ "$HAS_USERS" == "1" ]]; then
  printf '检测到现有数据库，跳过管理员创建。\n'
else
  cd "$INSTALL_DIR"
  runuser -u "$SERVICE_USER" -- "$INSTALL_DIR/.venv/bin/python" "$INSTALL_DIR/main.py" setup-admin
fi

printf '\n[5/7] 注册并启动后台服务...\n'
cp "$INSTALL_DIR/deploy/systemd/czon_agent.service" /etc/systemd/system/czon_agent.service
systemctl daemon-reload
systemctl enable --now czon_agent

printf '\n[6/7] 配置访问入口...\n'
if [[ "$USE_NGINX" == "y" ]]; then
  cp "$INSTALL_DIR/deploy/nginx/czon_agent.conf" /etc/nginx/sites-available/czon_agent
  ln -sfn /etc/nginx/sites-available/czon_agent /etc/nginx/sites-enabled/czon_agent
  rm -f /etc/nginx/sites-enabled/default
  nginx -t
  systemctl enable --now nginx
  systemctl reload nginx
fi

printf '\n[7/7] 检查服务...\n'
sleep 2
if ! systemctl is-active --quiet czon_agent; then
  systemctl status czon_agent --no-pager || true
  fail "czon_agent 没有正常启动，请查看上面的错误信息。"
fi

SERVER_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
SERVER_IP="${SERVER_IP:-服务器IP}"

printf '\n安装完成。\n'
if [[ "$USE_NGINX" == "y" ]]; then
  printf '访问地址：http://%s\n' "$SERVER_IP"
  printf '如果启用了防火墙，请放行 TCP 80；配置 HTTPS 时再放行 TCP 443。\n'
else
  printf '访问地址：http://%s:8000\n' "$SERVER_IP"
  printf '如果启用了防火墙，请放行 TCP 8000。\n'
fi
printf '首次登录后请立即修改初始密码，并在管理页面配置模型。\n'
