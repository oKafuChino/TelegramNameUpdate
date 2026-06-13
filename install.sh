#!/bin/bash

PROJECT_DIR="/opt/tg_updater"
REPO_URL="https://raw.githubusercontent.com/oKafuChino/TelegramNameUpdate/main"

# ==========================================
# 1. 补全系统基础依赖 (解决新机器无 venv 的问题)
# ==========================================
echo ">> 正在安装必要的系统环境 (python3-venv)..."
sudo apt-get update -y
sudo apt-get install -y python3-venv python3-pip curl

# ==========================================
# 2. 准备项目目录并从 GitHub 拉取核心文件
# ==========================================
echo ">> 正在从 GitHub 下载最新版本代码..."
sudo mkdir -p $PROJECT_DIR

sudo curl -sL "$REPO_URL/config.json" -o $PROJECT_DIR/config.json
sudo curl -sL "$REPO_URL/tg_daemon.py" -o $PROJECT_DIR/tg_daemon.py
sudo curl -sL "$REPO_URL/tg_panel.py" -o $PROJECT_DIR/tg_panel.py
sudo curl -sL "$REPO_URL/requirements.txt" -o $PROJECT_DIR/requirements.txt

sudo chmod +x $PROJECT_DIR/tg_panel.py
sudo chmod +x $PROJECT_DIR/tg_daemon.py

# ==========================================
# 3. 创建虚拟环境并安装依赖
# ==========================================
echo ">> 正在配置 Python 虚拟环境..."
# 加上 sudo，确保在 /opt 目录下拥有绝对权限
sudo python3 -m venv $PROJECT_DIR/venv
sudo $PROJECT_DIR/venv/bin/pip install -r $PROJECT_DIR/requirements.txt


# 4. 配置 systemd 服务
echo ">> 正在配置后台服务..."
cat << EOF | sudo tee /etc/systemd/system/tg_name.service
[Unit]
Description=Telegram Name Updater Daemon
After=network.target

[Service]
Type=simple
WorkingDirectory=$PROJECT_DIR
ExecStart=$PROJECT_DIR/venv/bin/python3 $PROJECT_DIR/tg_daemon.py
Restart=always
RestartSec=10
User=root

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable tg_name.service

# 5. 创建全局 'tg' 命令别名
echo ">> 正在配置快捷命令..."
sudo ln -sf $PROJECT_DIR/venv/bin/python3 /usr/local/bin/tg_py
cat << 'EOF' | sudo tee /usr/local/bin/tg
#!/bin/bash
sudo /usr/local/bin/tg_py /opt/tg_updater/tg_panel.py
EOF
sudo chmod +x /usr/local/bin/tg

echo "=================================="
echo "✅ 安装完成！"
echo "👉 请在终端输入 'tg' 打开控制面板，并使用选项 [1] 初始化账号。"
echo "=================================="