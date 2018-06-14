#!/bin/bash

name="webm2mp4bot"
desc="webm2mp4 Telegram bot"

echo "[Unit]
Description=$desc

[Service]
Type=simple
ExecStart=/usr/bin/python3 $PWD/bot.py
Restart=always
RestartSec=10
User=$USER
WorkingDirectory=$PWD

[Install]
WantedBy=multi-user.target" > $name.service

# apply
sudo mv $name.service /lib/systemd/system/
sudo systemctl daemon-reload && echo "Service: $name.service"
