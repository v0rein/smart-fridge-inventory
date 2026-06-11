#!/bin/bash

# SFI - Smart Fridge Inventory Raspberry Pi Installation Script
# Run this script directly on your Raspberry Pi

set -e

echo "================================================"
echo "SFI - Smart Fridge Inventory Automated Installer"
echo "================================================"

# 1. Update system and install dependencies
echo "[1/6] Updating system and installing dependencies..."
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv git curl libpq-dev libpq5

# Install Docker
if ! command -v docker &> /dev/null; then
    echo "Installing Docker..."
    # Menggunakan repositori bawaan OS untuk menghindari error repositori "trixie" yang belum didukung Docker resmi
    sudo apt install -y docker.io docker-compose-v2 || sudo apt install -y docker.io docker-compose
    sudo usermod -aG docker $USER
    echo "Docker installed. You may need to logout and login again for group changes to take effect."
else
    echo "Docker is already installed."
fi

# 2. Setup Project Directory
echo "[2/6] Setting up project directory..."
PROJECT_DIR=$(pwd)
echo "Setting up in current directory: $PROJECT_DIR"

# 3. Setup Python Virtual Environment
echo "[3/6] Setting up Python virtual environment..."
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 4. Configuration
echo "[4/6] Configuring Environment Variables..."
if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        cp .env.example .env
    else
        touch .env
    fi
fi

# Prompt for API keys
read -p "Enter PostgreSQL Database URL (e.g., postgresql://sfi_user:sfi_password@localhost:5432/sfi_db): " DB_URL
read -p "Enter Telegram Bot Token: " TELEGRAM_TOKEN
read -p "Enter Groq API Key: " GROQ_KEY

# Update .env
sed -i "s|^DATABASE_URL=.*|DATABASE_URL=${DB_URL}|g" .env
sed -i "s|^TELEGRAM_BOT_TOKEN=.*|TELEGRAM_BOT_TOKEN=${TELEGRAM_TOKEN}|g" .env
sed -i "s|^GROQ_API_KEY=.*|GROQ_API_KEY=${GROQ_KEY}|g" .env

# Fallback if sed didn't replace (e.g., lines didn't exist)
grep -q "^DATABASE_URL=" .env || echo "DATABASE_URL=$DB_URL" >> .env
grep -q "^TELEGRAM_BOT_TOKEN=" .env || echo "TELEGRAM_BOT_TOKEN=$TELEGRAM_TOKEN" >> .env
grep -q "^GROQ_API_KEY=" .env || echo "GROQ_API_KEY=$GROQ_KEY" >> .env

echo ".env file configured successfully."

# 5. Run PostgreSQL
echo "[5/6] Starting PostgreSQL via Docker..."
# Need to use sudo docker if group changes haven't taken effect in this shell session
sudo docker compose up -d || sudo docker-compose up -d

# 6. Setup Systemd Service
echo "[6/6] Setting up sfi-bot systemd service..."

SERVICE_FILE="/tmp/sfi-bot.service"

cat > $SERVICE_FILE << EOL
[Unit]
Description=SFI Telegram Bot
After=network.target docker.service

[Service]
Type=simple
User=$USER
WorkingDirectory=$PROJECT_DIR
ExecStart=$PROJECT_DIR/.venv/bin/python backend/bot.py
Restart=always
RestartSec=10
Environment=PATH=$PROJECT_DIR/.venv/bin:/usr/bin

[Install]
WantedBy=multi-user.target
EOL

sudo mv $SERVICE_FILE /etc/systemd/system/sfi-bot.service

sudo systemctl daemon-reload
sudo systemctl enable sfi-bot
sudo systemctl start sfi-bot

echo "================================================"
echo "Installation Complete!"
echo "Check bot status with: sudo systemctl status sfi-bot"
echo "Check logs with: sudo journalctl -u sfi-bot -f"
echo "================================================"
