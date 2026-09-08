#!/usr/bin/env bash
set -Eeuo pipefail

DOWNLOAD_URL="https://github.com/xi-pengfei/czon_agent/archive/refs/heads/main.zip"
INSTALL_DIR="/opt/czon_agent"
TEMP_DIR=""

fail() {
  printf '\n[下载失败] %s\n' "$1" >&2
  exit 1
}

cleanup() {
  if [[ -n "$TEMP_DIR" && -d "$TEMP_DIR" ]]; then
    rm -rf "$TEMP_DIR"
  fi
}
trap cleanup EXIT

if [[ "${EUID}" -ne 0 ]]; then
  fail "请使用 sudo bash 运行在线安装脚本。"
fi

if [[ -e "$INSTALL_DIR" ]] && find "$INSTALL_DIR" -mindepth 1 -print -quit | grep -q .; then
  fail "$INSTALL_DIR 已存在。为避免覆盖客户数据，在线安装已停止。"
fi

printf '\nczon_agent Ubuntu 在线安装\n'
printf '正在准备下载工具...\n'
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y ca-certificates curl unzip

TEMP_DIR="$(mktemp -d)"
ARCHIVE="$TEMP_DIR/czon_agent.zip"
printf '正在从 GitHub 下载最新版...\n'
curl --fail --location --retry 3 --connect-timeout 15 "$DOWNLOAD_URL" --output "$ARCHIVE"

printf '正在解压安装包...\n'
unzip -q "$ARCHIVE" -d "$TEMP_DIR"
SOURCE_DIR="$TEMP_DIR/czon_agent-main"
if [[ ! -f "$SOURCE_DIR/deploy/install_ubuntu.sh" ]]; then
  fail "下载内容不完整，请检查网络后重试。"
fi

bash "$SOURCE_DIR/deploy/install_ubuntu.sh"
