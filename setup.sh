#!/usr/bin/env bash
set -e
echo "=== 1. Updating packages ==="
apt-get update -y
apt-get install -y python3 python3-pip python3-venv git

echo "=== 2. Creating Python venv ==="
python3 -m venv /root/tg_assistant/venv
/root/tg_assistant/venv/bin/pip install --upgrade pip
/root/tg_assistant/venv/bin/pip install telethon aiogram httpx python-dotenv

echo "=== 3. Setting up systemd service ==="
cat << 'SERVICE_EOF' > /etc/systemd/system/tg_assistant.service
[Unit]
Description=PVZ TG Assistant Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/tg_assistant
ExecStart=/root/tg_assistant/venv/bin/python /root/tg_assistant/main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SERVICE_EOF

systemctl daemon-reload
echo "=== Setup complete! ==="
