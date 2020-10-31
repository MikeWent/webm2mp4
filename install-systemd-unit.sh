#!/bin/bash

name="webm2mp4bot"

sudo systemctl stop "$name.service" 2> /dev/null # hide output if service doesn't exist

echo "[Unit]
Description=webm2mp4 Telegram bot
Documentation=https://github.com/MikeWent/webm2mp4
Wants=network-online.target
After=network.target network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 $PWD/bot.py
Restart=always
RestartSec=5
User=$USER
WorkingDirectory=$PWD

[Install]
WantedBy=multi-user.target" > $name.service

sudo mv $name.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable "$name.service"
sudo systemctl start "$name.service"
echo "Service '$name.service' started and enabled on startup"
