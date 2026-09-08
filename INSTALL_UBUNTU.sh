#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

printf '\nczon_agent Ubuntu 安装程序\n'
printf '安装过程中需要输入当前 Ubuntu 账号的 sudo 密码。\n\n'
sudo bash "$PROJECT_DIR/deploy/install_ubuntu.sh"

printf '\n安装程序已经结束。\n'
if [[ -t 0 ]]; then
  read -r -p "按回车键关闭窗口..." _
fi
