# Smart Fridge Inventory (SFI) - Backend

Sistem inventaris kulkas pintar berbasis AI. Menggunakan kamera untuk mendeteksi produk secara otomatis, memantau tanggal kedaluwarsa, dan mengirim notifikasi via Telegram.

## Arsitektur

```
backend/
├── database/
│   ├── models.py      # Skema tabel (User, Inventory, ScanLog)
│   ├── crud.py        # Fungsi CRUD database
│   └── db.py          # Koneksi & session handling
├── intelligence/
│   └── ai_parser.py   # Groq VLM untuk analisis gambar (multi-item)
├── bot.py             # Bot Telegram (antarmuka utama)
DEPLOYMENT_RASPI.md    # Panduan deployment ke Raspberry Pi
docker-compose.yml     # PostgreSQL container
```

## Prasyarat

- Python 3.10+
- Docker Desktop (untuk PostgreSQL)
- API Key dari [Groq](https://console.groq.com/keys)
- Bot Token dari [@BotFather](https://t.me/BotFather)

## Setup Cepat

```bash
# 1. Jalankan PostgreSQL
docker compose up -d

# 2. Buat virtual environment
python -m venv .venv
.\.venv\Scripts\activate        # Windows
# source .venv/bin/activate     # Linux/Mac

# 3. Install dependencies
pip install -r requirements.txt

# 4. Konfigurasi environment
cp .env.example .env
# Isi: DATABASE_URL, TELEGRAM_BOT_TOKEN, GROQ_API_KEY

# 5. Jalankan bot
python backend/bot.py
```

## Fitur

| Fitur | Deskripsi |
|---|---|
| `/start` | Mendaftarkan user |
| `/help` | Panduan perintah |
| `/isikulkas` | Lihat semua stok |
| `/expired` | Cek barang mendekati kedaluwarsa |
| `/tambah` | Tambah barang manual |
| `/ambil` | Ambil/kurangi barang |
| Kirim foto | AI mengenali produk (mendukung multi-item dalam 1 foto) |
| Tanya jawab | Ketik pertanyaan natural tentang isi kulkas |
| Notifikasi | Peringatan otomatis setiap pagi (08:00 WIB) |

## Stack Teknologi

- **Database:** PostgreSQL (Docker) + SQLAlchemy ORM
- **Bot:** python-telegram-bot v20+
- **AI Vision:** Groq API — Llama 4 Scout (identifikasi produk, OCR, deteksi kesegaran)
- **AI Text:** Groq API — Llama 3.3 70B (tanya jawab natural)
- **Deployment:** Raspberry Pi 4B/5 + IP Camera (lihat `DEPLOYMENT_RASPI.md`)
