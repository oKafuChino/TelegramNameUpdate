#!/bin/bash

set -euo pipefail

PROJECT_DIR="/opt/tg_updater"
DATA_DIR="/var/lib/tg_updater"
REPO_URL="https://raw.githubusercontent.com/oKafuChino/TelegramNameUpdate/main"
SERVICE_USER="tg_updater"

if [ "$(id -u)" -eq 0 ]; then
    SUDO=""
else
    SUDO="sudo"
fi

SERVICE_WAS_ACTIVE=false
if $SUDO systemctl is-active --quiet tg_name.service 2>/dev/null; then
    SERVICE_WAS_ACTIVE=true
fi

# ==========================================
# 1. 补全系统基础依赖 (解决新机器无 venv 的问题)
# ==========================================
echo ">> 正在安装必要的系统环境 (python3-venv)..."
$SUDO apt-get update -y
$SUDO apt-get install -y python3-venv curl

if ! id -u "$SERVICE_USER" >/dev/null 2>&1; then
    $SUDO useradd --system --home "$DATA_DIR" --shell /usr/sbin/nologin "$SERVICE_USER"
fi

# ==========================================
# 2. 准备项目目录并从 GitHub 拉取核心文件
# ==========================================
echo ">> 正在从 GitHub 下载最新版本代码..."
for target_dir in "$PROJECT_DIR" "$DATA_DIR"; do
    if $SUDO test -L "$target_dir"; then
        echo ">> 安装失败：目标目录不能是符号链接: $target_dir" >&2
        exit 1
    fi
    if $SUDO test -e "$target_dir" && ! $SUDO test -d "$target_dir"; then
        echo ">> 安装失败：目标路径不是目录: $target_dir" >&2
        exit 1
    fi
done
$SUDO mkdir -p "$PROJECT_DIR"
$SUDO mkdir -p "$DATA_DIR"

TMP_DIR="$(mktemp -d)"
cleanup_tmp_dir() {
    $SUDO rm -rf -- "$TMP_DIR"
}
trap cleanup_tmp_dir EXIT

download_file() {
    curl -fsSL --connect-timeout 10 --max-time 30 --retry 3 --retry-delay 2 \
        --retry-connrefused --max-filesize 2097152 "$1" -o "$2"
    if [ "$(wc -c < "$2")" -gt 2097152 ]; then
        echo ">> 下载文件超过 2 MiB 限制: $1" >&2
        return 1
    fi
}

download_file "$REPO_URL/tg_daemon.py" "$TMP_DIR/tg_daemon.py"
download_file "$REPO_URL/tg_panel.py" "$TMP_DIR/tg_panel.py"
download_file "$REPO_URL/requirements.txt" "$TMP_DIR/requirements.txt"

python3 -c 'import ast, pathlib, sys
required = {"tg_daemon.py": {"main", "change_name_auto"}, "tg_panel.py": {"CURRENT_VERSION", "main_menu"}}
for path in sys.argv[1:]:
    tree = ast.parse(pathlib.Path(path).read_text(encoding="utf-8"), filename=path)
    symbols = {node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            symbols.update(target.id for target in node.targets if isinstance(target, ast.Name))
    missing = required[pathlib.Path(path).name] - symbols
    if missing:
        raise SystemExit(f"missing required symbols in {path}: {sorted(missing)}")' \
    "$TMP_DIR/tg_daemon.py" "$TMP_DIR/tg_panel.py"

DAEMON_EXISTED=false
PANEL_EXISTED=false
REQUIREMENTS_EXISTED=false
if $SUDO test -f "$PROJECT_DIR/tg_daemon.py"; then
    $SUDO cp -p "$PROJECT_DIR/tg_daemon.py" "$TMP_DIR/tg_daemon.py.backup"
    DAEMON_EXISTED=true
fi
if $SUDO test -f "$PROJECT_DIR/tg_panel.py"; then
    $SUDO cp -p "$PROJECT_DIR/tg_panel.py" "$TMP_DIR/tg_panel.py.backup"
    PANEL_EXISTED=true
fi
if $SUDO test -f "$PROJECT_DIR/requirements.txt"; then
    $SUDO cp -p "$PROJECT_DIR/requirements.txt" "$TMP_DIR/requirements.txt.backup"
    REQUIREMENTS_EXISTED=true
fi

if ! $SUDO install -m 755 "$TMP_DIR/tg_daemon.py" "$PROJECT_DIR/tg_daemon.py" || \
   ! $SUDO install -m 755 "$TMP_DIR/tg_panel.py" "$PROJECT_DIR/tg_panel.py" || \
   ! $SUDO install -m 644 "$TMP_DIR/requirements.txt" "$PROJECT_DIR/requirements.txt"; then
    echo ">> 核心文件安装失败，正在恢复旧版本..."
    if $DAEMON_EXISTED; then $SUDO install -m 755 "$TMP_DIR/tg_daemon.py.backup" "$PROJECT_DIR/tg_daemon.py"; else $SUDO rm -f "$PROJECT_DIR/tg_daemon.py"; fi
    if $PANEL_EXISTED; then $SUDO install -m 755 "$TMP_DIR/tg_panel.py.backup" "$PROJECT_DIR/tg_panel.py"; else $SUDO rm -f "$PROJECT_DIR/tg_panel.py"; fi
    if $REQUIREMENTS_EXISTED; then $SUDO install -m 644 "$TMP_DIR/requirements.txt.backup" "$PROJECT_DIR/requirements.txt"; else $SUDO rm -f "$PROJECT_DIR/requirements.txt"; fi
    exit 1
fi

if [ -f "$PROJECT_DIR/api_auth.json" ] && [ ! -f "$DATA_DIR/api_auth.json" ]; then
    $SUDO mv "$PROJECT_DIR/api_auth.json" "$DATA_DIR/api_auth.json"
fi
if [ -f "$PROJECT_DIR/api_auth.session" ] && [ ! -f "$DATA_DIR/api_auth.session" ]; then
    $SUDO mv "$PROJECT_DIR/api_auth.session" "$DATA_DIR/api_auth.session"
fi
if [ -f "$PROJECT_DIR/api_auth.session-journal" ] && [ ! -f "$DATA_DIR/api_auth.session-journal" ]; then
    $SUDO mv "$PROJECT_DIR/api_auth.session-journal" "$DATA_DIR/api_auth.session-journal"
fi
if [ ! -f "$DATA_DIR/config.json" ]; then
    download_file "$REPO_URL/config.json" "$TMP_DIR/config.json"
    python3 -c 'import json, pathlib, sys; json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))' "$TMP_DIR/config.json"
    $SUDO install -m 600 "$TMP_DIR/config.json" "$DATA_DIR/config.json"
fi

# ==========================================
# 3. 创建虚拟环境并安装依赖
# ==========================================
echo ">> 正在配置 Python 虚拟环境..."
if [ ! -x "$PROJECT_DIR/venv/bin/python3" ]; then
    $SUDO python3 -m venv "$PROJECT_DIR/venv"
fi
$SUDO "$PROJECT_DIR/venv/bin/pip" install --no-cache-dir --no-compile -r "$PROJECT_DIR/requirements.txt"
$SUDO chown -R root:root "$PROJECT_DIR"
$SUDO chmod 755 "$PROJECT_DIR"
$SUDO chown -R "$SERVICE_USER:$SERVICE_USER" "$DATA_DIR"
$SUDO chmod 700 "$DATA_DIR"
$SUDO find "$DATA_DIR" -type f -exec chmod 600 {} \;


# 4. 配置 systemd 服务
echo ">> 正在配置后台服务..."
cat << EOF | $SUDO tee /etc/systemd/system/tg_name.service
[Unit]
Description=Telegram Name Updater Daemon
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
WorkingDirectory=$PROJECT_DIR
ExecStart=$PROJECT_DIR/venv/bin/python3 $PROJECT_DIR/tg_daemon.py
Environment=TG_UPDATER_DATA_DIR=$DATA_DIR
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONDONTWRITEBYTECODE=1
Restart=always
RestartSec=10
User=$SERVICE_USER
Group=$SERVICE_USER
UMask=0077
NoNewPrivileges=true
CapabilityBoundingSet=
AmbientCapabilities=
PrivateTmp=true
PrivateDevices=true
ProtectHome=true
ProtectSystem=full
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
RestrictRealtime=true
LockPersonality=true
MemoryDenyWriteExecute=true
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
ReadWritePaths=$DATA_DIR

[Install]
WantedBy=multi-user.target
EOF

$SUDO systemctl daemon-reload
$SUDO systemctl enable tg_name.service
if $SERVICE_WAS_ACTIVE; then
    $SUDO systemctl restart tg_name.service
fi

# 5. 创建全局 'tg' 命令别名
echo ">> 正在配置快捷命令..."
$SUDO ln -sf "$PROJECT_DIR/venv/bin/python3" /usr/local/bin/tg_py
cat << 'EOF' | $SUDO tee /usr/local/bin/tg
#!/bin/bash
sudo /usr/local/bin/tg_py /opt/tg_updater/tg_panel.py
EOF
$SUDO chmod +x /usr/local/bin/tg

echo "=================================="
echo "✅ 安装完成！"
echo "👉 请在终端输入 'tg' 打开控制面板，并使用选项 [1] 初始化账号。"
echo "=================================="
