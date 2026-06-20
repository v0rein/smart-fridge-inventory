#!/bin/bash

# SFI - Smart Fridge Inventory Raspberry Pi Installation Script
# Run this script directly on your Raspberry Pi
# Mendukung Raspberry Pi 3 (1GB RAM) dengan mode SQLite (tanpa Docker)

set -e

echo "================================================"
echo "SFI - Smart Fridge Inventory Automated Installer"
echo "================================================"

# Deteksi RAM untuk rekomendasi otomatis
TOTAL_RAM_MB=$(free -m | awk '/^Mem:/{print $2}')
echo "RAM terdeteksi: ${TOTAL_RAM_MB} MB"

if [ "$TOTAL_RAM_MB" -lt 2048 ]; then
    echo ""
    echo "⚠️  RAM kurang dari 2GB. Direkomendasikan menggunakan SQLite (tanpa Docker)."
    echo "   Ini akan menghemat ~300MB RAM."
    USE_SQLITE_DEFAULT="y"
else
    USE_SQLITE_DEFAULT="n"
fi

# Tanyakan user mau pakai SQLite atau PostgreSQL
echo ""
read -p "Gunakan SQLite (ringan, tanpa Docker)? [Y/n]: " USE_SQLITE
USE_SQLITE=${USE_SQLITE:-$USE_SQLITE_DEFAULT}

# 1. Update system and install dependencies
echo "[1/7] Updating system and installing dependencies..."
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv git curl

# Install library tambahan yang diperlukan
if [[ "$USE_SQLITE" =~ ^[Nn]$ ]]; then
    sudo apt install -y libpq-dev libpq5 libopenblas-dev
else
    sudo apt install -y libopenblas-dev
fi

# Install Docker HANYA jika user pilih PostgreSQL
if [[ "$USE_SQLITE" =~ ^[Nn]$ ]]; then
    if ! command -v docker &> /dev/null; then
        echo "Installing Docker..."
        sudo apt install -y docker.io docker-compose-v2 || sudo apt install -y docker.io docker-compose
        sudo usermod -aG docker $USER
        echo "Docker installed. You may need to logout and login again for group changes to take effect."
    else
        echo "Docker is already installed."
    fi
else
    echo "Mode SQLite dipilih — Docker tidak diperlukan, skip instalasi Docker."
fi

# 2. Setup Swap (penting untuk Pi 3 dengan RAM terbatas)
echo "[2/7] Mengatur swap file..."
if [ "$TOTAL_RAM_MB" -lt 2048 ]; then
    CURRENT_SWAP=$(free -m | awk '/^Swap:/{print $2}')
    if [ "$CURRENT_SWAP" -lt 512 ]; then
        echo "Memperbesar swap ke 1024MB untuk keamanan..."
        sudo dphys-swapfile swapoff 2>/dev/null || true
        sudo sed -i 's/^CONF_SWAPSIZE=.*/CONF_SWAPSIZE=1024/' /etc/dphys-swapfile
        sudo dphys-swapfile setup
        sudo dphys-swapfile swapon
        echo "Swap berhasil diperbesar ke 1024MB."
    else
        echo "Swap sudah cukup (${CURRENT_SWAP}MB). Skip."
    fi
else
    echo "RAM cukup besar (${TOTAL_RAM_MB}MB). Skip konfigurasi swap."
fi

# 3. Setup Project Directory
echo "[3/7] Setting up project directory..."
PROJECT_DIR=$(pwd)
echo "Setting up in current directory: $PROJECT_DIR"

# 4. Setup Python Virtual Environment
echo "[4/7] Setting up Python virtual environment..."
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 5. Configuration
echo "[5/7] Configuring Environment Variables..."
if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        cp .env.example .env
    else
        touch .env
    fi
fi

# Konfigurasi Database URL
if [[ "$USE_SQLITE" =~ ^[Nn]$ ]]; then
    read -p "Enter PostgreSQL Database URL (e.g., postgresql://sfi_user:sfi_password@localhost:5432/sfi_db): " DB_URL
else
    DB_URL="sqlite:///./sfi_database.db"
    echo "Menggunakan SQLite: $DB_URL"
fi

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

# Generate ENCRYPTION_KEY for cryptography if it's empty or placeholder
if ! grep -q "^ENCRYPTION_KEY=" .env || grep -q "isi_dengan_fernet_key" .env; then
    echo "Generating new ENCRYPTION_KEY..."
    # Hilangkan placeholder lama
    sed -i '/^ENCRYPTION_KEY=.*$/d' .env
    # Generate key baru pakai python cryptography dari venv
    NEW_KEY=$($PROJECT_DIR/.venv/bin/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
    echo "ENCRYPTION_KEY=$NEW_KEY" >> .env
fi

echo ".env file configured successfully."

# 6. Run PostgreSQL (hanya jika user pilih PostgreSQL)
echo "[6/7] Database setup..."
if [[ "$USE_SQLITE" =~ ^[Nn]$ ]]; then
    echo "Starting PostgreSQL via Docker..."
    sudo docker compose up -d || sudo docker-compose up -d
else
    echo "Mode SQLite — tidak perlu menjalankan Docker. Database akan otomatis dibuat saat bot pertama kali dijalankan."
fi

# 7. Setup Systemd Service
echo "[7/7] Setting up sfi-bot systemd service..."

SERVICE_FILE="/tmp/sfi-bot.service"

cat > $SERVICE_FILE << EOL
[Unit]
Description=SFI Telegram Bot
After=network.target$(if [[ "$USE_SQLITE" =~ ^[Nn]$ ]]; then echo " docker.service"; fi)

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
echo ""
echo "Database Mode: $(if [[ "$USE_SQLITE" =~ ^[Nn]$ ]]; then echo 'PostgreSQL (Docker)'; else echo 'SQLite (ringan)'; fi)"
echo "RAM: ${TOTAL_RAM_MB}MB | Swap: $(free -m | awk '/^Swap:/{print $2}')MB"
echo ""
echo "Check bot status with: sudo systemctl status sfi-bot"
echo "Check logs with: sudo journalctl -u sfi-bot -f"
echo "================================================"
