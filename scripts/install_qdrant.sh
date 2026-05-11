#!/bin/bash
# Qdrant 一键安装脚本（macOS）
# 用法：bash scripts/install_qdrant.sh
# 功能：下载 Qdrant 二进制 → 存到项目本地运行目录

set -e

QDRANT_VERSION="v1.13.4"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DATA_DIR="$PROJECT_ROOT/data/qdrant"
BIN_DIR="$PROJECT_ROOT/.runtime/qdrant/bin"

echo ">>> 检测系统架构..."
ARCH=$(uname -m)
if [ "$ARCH" = "arm64" ]; then
    BINARY="qdrant-aarch64-apple-darwin.tar.gz"
    echo "    Apple Silicon (M1/M2/M3)"
else
    BINARY="qdrant-x86_64-apple-darwin.tar.gz"
    echo "    Intel"
fi

DOWNLOAD_URL="https://github.com/qdrant/qdrant/releases/download/${QDRANT_VERSION}/${BINARY}"

echo ">>> 创建目录..."
mkdir -p "$DATA_DIR" "$BIN_DIR"

echo ">>> 下载 Qdrant ${QDRANT_VERSION}..."
TMP_DIR=$(mktemp -d)
if ! curl --http1.1 --fail --location --progress-bar \
    --retry 3 --retry-delay 2 --retry-all-errors \
    "$DOWNLOAD_URL" -o "$TMP_DIR/qdrant.tar.gz"; then
    echo "❌ 下载失败：$DOWNLOAD_URL"
    echo "   请检查网络或稍后重试。"
    rm -rf "$TMP_DIR"
    exit 1
fi

echo ">>> 安装二进制..."
tar -xzf "$TMP_DIR/qdrant.tar.gz" -C "$TMP_DIR"
cp "$TMP_DIR/qdrant" "$BIN_DIR/qdrant"
chmod +x "$BIN_DIR/qdrant"
rm -rf "$TMP_DIR"
echo "    已安装到 $BIN_DIR/qdrant"

echo ">>> 检测端口 6333 占用..."
PORT_PID=$(lsof -ti tcp:6333 2>/dev/null || true)
if [ -n "$PORT_PID" ]; then
    PORT_CMD=$(ps -p "$PORT_PID" -o comm= 2>/dev/null || echo "unknown")
    echo "    ⚠️  端口 6333 已被进程 $PORT_PID ($PORT_CMD) 占用"
    echo "    安装已完成；Agent 启动时会在端口空闲后自动拉起项目内 Qdrant。"
else
    echo ">>> 端口空闲。安装完成后，启动 Agent 会自动拉起 Qdrant。"
fi

echo ""
echo "✅ Qdrant 二进制安装成功！"
echo "   二进制：$BIN_DIR/qdrant"
echo "   数据目录：$DATA_DIR"
echo "   日志文件：$DATA_DIR/qdrant.log"
echo "   启动方式：python main.py webui / python main.py / python main.py \"消息\""
