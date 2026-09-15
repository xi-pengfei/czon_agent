#!/usr/bin/env bash
set -Eeuo pipefail
export COPYFILE_DISABLE=1

VERSION="${1:-1.0.0}"
PYTHON_VERSION="3.12.10"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_ROOT="$PROJECT_ROOT/.packaging-build/macos"
PAYLOAD_ROOT="$BUILD_ROOT/payload"
INSTALL_DIR="$PAYLOAD_ROOT/Applications/czon_agent"
SCRIPT_ROOT="$BUILD_ROOT/scripts"
RELEASE_ROOT="$PROJECT_ROOT/release/macos"
ARCH="$(uname -m)"
VALIDATION_VENV="$BUILD_ROOT/validation-venv"
DOWNLOAD_PYTHON="$PROJECT_ROOT/.venv/bin/python"
OUTPUT="$RELEASE_ROOT/czon_agent_${VERSION}_macos_${ARCH}.pkg"
RELEASE_UNINSTALLER="$RELEASE_ROOT/卸载企业 AI 智能体.app"

if [[ ! "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  printf '版本号必须采用 1.0.0 格式。\n' >&2
  exit 1
fi
if [[ "$ARCH" != "arm64" && "$ARCH" != "x86_64" ]]; then
  printf '不支持当前 macOS 架构：%s\n' "$ARCH" >&2
  exit 1
fi

for required_command in curl ditto osacompile pkgbuild rsync python3 xattr; do
  command -v "$required_command" >/dev/null || {
    printf '缺少构建命令：%s\n' "$required_command" >&2
    exit 1
  }
done
if [[ "$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')" != "3.12" ]]; then
  printf '构建电脑的 python3 必须是 Python 3.12。\n' >&2
  exit 1
fi
if [[ ! -x "$DOWNLOAD_PYTHON" ]]; then
  DOWNLOAD_PYTHON="python3"
fi

rm -rf "$BUILD_ROOT"
rm -f "$OUTPUT"
rm -rf "$RELEASE_UNINSTALLER"
mkdir -p "$INSTALL_DIR/.installer/wheelhouse" "$SCRIPT_ROOT" "$RELEASE_ROOT"

printf '[1/6] 整理安装内容...\n'
for runtime_dir in adapters core tools_builtin webui; do
  rsync -a \
    --exclude '__pycache__/' \
    --exclude '*.pyc' \
    --exclude '.DS_Store' \
    "$PROJECT_ROOT/$runtime_dir/" "$INSTALL_DIR/$runtime_dir/"
done

cp -X "$PROJECT_ROOT/main.py" "$PROJECT_ROOT/config.yaml" \
  "$PROJECT_ROOT/requirements.txt" "$INSTALL_DIR/"

# The base installer contains only generic system Skills. Customer-specific
# Skills are managed separately after installation.
for system_skill in office-io enterprise-skill-creator; do
  mkdir -p "$INSTALL_DIR/skills/$system_skill"
  rsync -a \
    --exclude '__pycache__/' \
    --exclude '*.pyc' \
    --exclude '.DS_Store' \
    "$PROJECT_ROOT/skills/$system_skill/" "$INSTALL_DIR/skills/$system_skill/"
done

mkdir -p "$INSTALL_DIR/data" "$INSTALL_DIR/logs" "$INSTALL_DIR/uploads" "$INSTALL_DIR/workspace"
APP_BUNDLE="$PAYLOAD_ROOT/Applications/企业 AI 智能体.app"
osacompile -o "$APP_BUNDLE" -e 'open location "http://127.0.0.1:8000"'
cp -X "$PROJECT_ROOT/packaging/macos/czon_agent.icns" "$APP_BUNDLE/Contents/Resources/applet.icns"
UNINSTALLER_BUNDLE="$PAYLOAD_ROOT/Applications/卸载企业 AI 智能体.app"
osacompile -o "$UNINSTALLER_BUNDLE" "$PROJECT_ROOT/packaging/macos/uninstall.applescript"
cp -X "$PROJECT_ROOT/packaging/macos/czon_agent.icns" "$UNINSTALLER_BUNDLE/Contents/Resources/applet.icns"

printf '[2/6] 下载官方 Python 安装程序...\n'
curl --fail --location --retry 3 \
  "https://www.python.org/ftp/python/$PYTHON_VERSION/python-$PYTHON_VERSION-macos11.pkg" \
  --output "$INSTALL_DIR/.installer/python.pkg"

printf '[3/6] 准备离线 Python 依赖...\n'
"$DOWNLOAD_PYTHON" -m pip download \
  --only-binary=:all: \
  --implementation cp \
  --python-version 312 \
  --abi cp312 \
  --platform "macosx_11_0_$ARCH" \
  --dest "$INSTALL_DIR/.installer/wheelhouse" \
  --requirement "$PROJECT_ROOT/requirements.txt"

printf '[4/6] 验证安装包依赖和程序测试...\n'
python3 -m venv "$VALIDATION_VENV"
"$VALIDATION_VENV/bin/python" -m pip install \
  --disable-pip-version-check \
  --no-index \
  --find-links "$INSTALL_DIR/.installer/wheelhouse" \
  -r "$PROJECT_ROOT/requirements.txt"
"$VALIDATION_VENV/bin/python" -m unittest discover -s "$PROJECT_ROOT/tests" -p 'test_*.py'

printf '[5/6] 准备启动配置...\n'
cp -X "$PROJECT_ROOT/packaging/macos/com.czon.agent.plist" "$INSTALL_DIR/.installer/"
cp -X "$PROJECT_ROOT/packaging/macos/postinstall" "$SCRIPT_ROOT/postinstall"
chmod 755 "$SCRIPT_ROOT/postinstall"
xattr -cr "$PAYLOAD_ROOT" "$SCRIPT_ROOT"

printf '[6/6] 生成 macOS 安装包...\n'
pkgbuild \
  --root "$PAYLOAD_ROOT" \
  --scripts "$SCRIPT_ROOT" \
  --identifier "com.czon.agent" \
  --version "$VERSION" \
  --install-location / \
  "$OUTPUT"

/usr/bin/ditto "$UNINSTALLER_BUNDLE" "$RELEASE_UNINSTALLER"

printf '安装包已生成：%s\n' "$OUTPUT"
printf '独立卸载程序已生成：%s\n' "$RELEASE_UNINSTALLER"
