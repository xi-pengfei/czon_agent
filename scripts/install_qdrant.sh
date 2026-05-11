#!/bin/bash
# Qdrant 一键安装脚本（macOS）
# 用法：bash scripts/install_qdrant.sh
# 功能：下载 Qdrant 二进制 → 存到本地 → 配置开机自启

set -e

QDRANT_VERSION="v1.13.4"
DATA_DIR="$HOME/data/qdrant"
BIN_DIR="$HOME/.local/bin"
PLIST_PATH="$HOME/Library/LaunchAgents/io.qdrant.server.plist"

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
curl -L --progress-bar "$DOWNLOAD_URL" -o "$TMP_DIR/qdrant.tar.gz"

echo ">>> 安装二进制..."
tar -xzf "$TMP_DIR/qdrant.tar.gz" -C "$TMP_DIR"
cp "$TMP_DIR/qdrant" "$BIN_DIR/qdrant"
chmod +x "$BIN_DIR/qdrant"
rm -rf "$TMP_DIR"
echo "    已安装到 $BIN_DIR/qdrant"

echo ">>> 配置开机自启（launchd）..."
cat > "$PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>io.qdrant.server</string>
    <key>ProgramArguments</key>
    <array>
        <string>$BIN_DIR/qdrant</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$DATA_DIR</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$DATA_DIR/qdrant.log</string>
    <key>StandardErrorPath</key>
    <string>$DATA_DIR/qdrant.log</string>
</dict>
</plist>
EOF

echo ">>> 检测端口 6333 占用..."
PORT_PID=$(lsof -ti tcp:6333 2>/dev/null || true)
if [ -n "$PORT_PID" ]; then
    PORT_CMD=$(ps -p "$PORT_PID" -o comm= 2>/dev/null || echo "unknown")
    echo "    ⚠️  端口 6333 已被进程 $PORT_PID ($PORT_CMD) 占用"
    echo "    请先停止旧服务再重试，例如："
    echo "      launchctl unload ~/Library/LaunchAgents/io.qdrant.server.plist"
    echo "      或 kill $PORT_PID"
    exit 1
fi

echo ">>> 启动 Qdrant..."
# 如果已经加载过，先卸载
launchctl unload "$PLIST_PATH" 2>/dev/null || true
launchctl load "$PLIST_PATH"

echo ">>> 等待启动..."
sleep 3

echo ">>> 验证（确认是本次安装的 launchd 进程）..."
RUNNING_PID=$(launchctl list | awk '/io\.qdrant\.server/ {print $1}' | grep -v '-' || true)
if [ -z "$RUNNING_PID" ]; then
    echo "❌ launchd 进程未运行，查看日志：cat $DATA_DIR/qdrant.log"
    exit 1
fi

if curl -s http://localhost:6333/healthz | grep -q "passed"; then
    echo ""
    echo "✅ Qdrant 安装成功！（launchd PID: $RUNNING_PID）"
    echo "   数据目录：$DATA_DIR"
    echo "   日志文件：$DATA_DIR/qdrant.log"
    echo "   开机自动启动：已配置"
    echo ""
    echo "   停止服务：launchctl unload $PLIST_PATH"
    echo "   启动服务：launchctl load $PLIST_PATH"
else
    echo "❌ 进程已启动但 healthz 未通过，查看日志：cat $DATA_DIR/qdrant.log"
    exit 1
fi
