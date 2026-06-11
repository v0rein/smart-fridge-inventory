# Panduan Deployment Raspberry Pi - Smart Fridge Inventory

## Arsitektur Hardware

```
┌────────────────────────────────────────┐
│              KULKAS                     │
│                                        │
│  ┌──────────┐                          │
│  │ IP Camera│◄── Mount di atas pintu   │
│  │ (WiFi)   │    kulkas, menghadap     │
│  └────┬─────┘    area masuk barang     │
│       │                                │
└───────┼────────────────────────────────┘
        │ WiFi / Ethernet
        ▼
┌───────────────────┐
│   Raspberry Pi    │
│   (Model 4B/5)    │
│                   │
│  - Python Bot     │
│  - PostgreSQL     │
│  - Docker         │
│                   │
│  Power: USB-C 5V  │
└───────────────────┘
        │ WiFi / Ethernet
        ▼
    ┌────────┐
    │Internet│ ──► Telegram API + Groq API
    └────────┘
```

## Kebutuhan Hardware

| Komponen | Spesifikasi | Perkiraan Harga |
|---|---|---|
| Raspberry Pi 4B / 5 | RAM 4GB (minimal) | Rp 900.000 - 1.200.000 |
| Power Supply | USB-C 5V 3A | Rp 100.000 |
| MicroSD Card | 32GB Class 10 (minimal) | Rp 80.000 |
| IP Camera (WiFi) | Resolusi 1080p, mendukung RTSP/MJPEG | Rp 200.000 - 500.000 |
| Kabel Ethernet (opsional) | Cat5e | Rp 30.000 |

**Total perkiraan: Rp 1.300.000 - 1.900.000**

> Catatan: Raspberry Pi tidak perlu kamera module (CSI). Kita menggunakan IP Camera terpisah yang terhubung via WiFi karena lebih fleksibel untuk penempatan.

## Wiring / Koneksi

Karena menggunakan IP Camera (bukan kamera langsung di GPIO), **tidak ada wiring kabel khusus**. Semua terhubung via jaringan:

1. **Raspberry Pi** — colok power USB-C, hubungkan ke WiFi router / Ethernet
2. **IP Camera** — colok power adaptor, hubungkan ke WiFi yang sama dengan Raspberry Pi
3. Pastikan keduanya berada di **jaringan lokal yang sama**

```
[Router WiFi]
    ├── Raspberry Pi (192.168.1.x)
    └── IP Camera   (192.168.1.y)
```

## Setup Raspberry Pi

### Cara Otomatis (Direkomendasikan)
Kami telah menyediakan script instalasi otomatis yang akan menjalankan semua langkah di bawah secara otomatis. 
1. Pastikan Anda sudah menginstall Raspberry Pi OS (langkah 1 di bawah).
2. Salin folder proyek ke Raspberry Pi, atau clone repository:
   ```bash
   git clone https://github.com/v0rein/smart-fridge-inventory ~/sfi
   cd ~/sfi
   ```
3. Beri izin eksekusi dan jalankan script:
   ```bash
   chmod +x install_raspi.sh
   ./install_raspi.sh
   ```
4. Script akan meminta Anda untuk memasukkan `DATABASE_URL`, `TELEGRAM_BOT_TOKEN`, dan `GROQ_API_KEY`. Setelah selesai, bot Anda akan otomatis berjalan.

---

### Cara Manual

Jika Anda lebih suka mengatur semuanya secara manual, ikuti langkah-langkah berikut:

### 1. Install OS
Flash **Raspberry Pi OS (64-bit Lite)** ke MicroSD menggunakan [Raspberry Pi Imager](https://www.raspberrypi.com/software/). Aktifkan SSH saat flashing.

### 2. Install Dependencies
```bash
# Update sistem
sudo apt update && sudo apt upgrade -y

# Install Python, pip, dan Git
sudo apt install -y python3 python3-pip python3-venv git curl

# Install Docker (untuk PostgreSQL)
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# Logout lalu login kembali agar group aktif
```

### 3. Clone & Setup Project
```bash
git clone https://github.com/v0rein/smart-fridge-inventory ~/sfi
cd ~/sfi

# Buat virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 4. Konfigurasi Environment
```bash
cp .env.example .env
nano .env
# Isi: DATABASE_URL, TELEGRAM_BOT_TOKEN, GROQ_API_KEY
```

### 5. Jalankan PostgreSQL
```bash
sudo docker compose up -d
```

### 6. Jalankan Bot sebagai Service (Auto-start)
Buat systemd service agar bot otomatis jalan saat Raspberry Pi dinyalakan:

```bash
sudo nano /etc/systemd/system/sfi-bot.service
```

Isi dengan:
```ini
[Unit]
Description=SFI Telegram Bot
After=network.target docker.service

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/sfi
ExecStart=/home/pi/sfi/.venv/bin/python backend/bot.py
Restart=always
RestartSec=10
Environment=PATH=/home/pi/sfi/.venv/bin:/usr/bin

[Install]
WantedBy=multi-user.target
```

Aktifkan:
```bash
sudo systemctl daemon-reload
sudo systemctl enable sfi-bot
sudo systemctl start sfi-bot

# Cek status
sudo systemctl status sfi-bot
```

## Integrasi IP Camera (Opsional - Untuk Auto-Capture)

Jika ingin menambahkan fitur auto-capture (kamera otomatis mengambil foto saat pintu kulkas dibuka), Anda bisa menambahkan script tambahan:

```bash
# Install OpenCV
pip install opencv-python-headless
```

Contoh script capture (`backend/camera_capture.py`):
```python
import cv2
import time

# Ganti dengan URL stream IP Camera Anda
CAMERA_URL = "rtsp://admin:password@192.168.1.y:554/stream1"

cap = cv2.VideoCapture(CAMERA_URL)
if cap.isOpened():
    ret, frame = cap.read()
    if ret:
        cv2.imwrite("/tmp/fridge_capture.jpg", frame)
        print("Foto berhasil diambil")
cap.release()
```

> Catatan: Fitur auto-capture ini opsional. Untuk demo awal, cukup kirim foto manual via Telegram.

## Troubleshooting

| Masalah | Solusi |
|---|---|
| Bot tidak jalan setelah reboot | Cek `sudo systemctl status sfi-bot` |
| Tidak bisa connect ke PostgreSQL | Pastikan Docker berjalan: `docker ps` |
| IP Camera tidak terdeteksi | Pastikan 1 jaringan WiFi, cek IP di router |
| Groq API timeout | Pastikan koneksi internet Raspberry Pi stabil |
