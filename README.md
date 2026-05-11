# 🧊 Smart Fridge Inventory (SFI)

> Sistem manajemen inventaris bahan makanan berbasis IoT & AI — otomatis, cerdas, dan tanpa ribet.

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://python.org)
[![Telegram Bot](https://img.shields.io/badge/Telegram-Bot%20API-26A5E4?logo=telegram&logoColor=white)](https://core.telegram.org/bots/api)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Groq](https://img.shields.io/badge/Groq-Llama%204%20Scout-F55036)](https://groq.com)
[![License](https://img.shields.io/badge/License-Academic-lightgrey)]()

---

## 📖 Tentang Proyek

**Smart Fridge Inventory (SFI)** adalah sistem manajemen inventaris kulkas otomatis yang dirancang agar pengguna **tidak perlu melakukan input manual**. Cukup kirim foto barang belanjaan ke Telegram Bot, dan sistem akan secara otomatis:

- 🔍 **Mengidentifikasi produk** menggunakan AI (LLM Vision)
- 📅 **Membaca tanggal kedaluwarsa** dari kemasan (OCR via AI)
- 📦 **Mencatat & mengelola stok** secara real-time
- ⏰ **Mengirim notifikasi** harian untuk barang yang mendekati expired
- 💬 **Menjawab pertanyaan** natural language tentang isi kulkas

Proyek ini dikembangkan sebagai **Capstone Project** di Jurusan Teknologi Informasi, Institut Teknologi Sepuluh Nopember (ITS).

---

## ✨ Fitur Utama

| Fitur | Deskripsi | Status |
|---|---|---|
| **AI Scanner** | Kirim foto → AI mendeteksi nama, kategori, jumlah, & estimasi expiry | ✅ |
| **Multi-item Detection** | Satu foto bisa mendeteksi banyak barang sekaligus | ✅ |
| **Smart Check-in** | Barang baru ditambahkan, barang lama ditambah stoknya | ✅ |
| **Manual Check-in** | `/tambah` untuk input manual dengan kategori & satuan | ✅ |
| **Check-out / Partial** | `/ambil` untuk mengeluarkan barang (full / sebagian) | ✅ |
| **Notifikasi Harian** | Peringatan otomatis jam 08:00 WIB untuk barang H-3 expired | ✅ |
| **Natural Language Query** | Tanya apapun tentang isi kulkas dalam bahasa natural | ✅ |
| **Enkripsi Chat ID** | Data Telegram Chat ID dienkripsi dengan Fernet (SKPL-NF04) | ✅ |

---

## 🏗️ Arsitektur Sistem

```
┌─────────────────────┐          ┌───────────────────────────────┐
│   Pengguna           │          │        SFI Backend (Python)   │
│   (Telegram App)     │◄────────►│                               │
└─────────────────────┘  Bot API  │  ┌─────────┐  ┌───────────┐  │
                                  │  │  bot.py  │  │ database/ │  │
                                  │  │ (Handler)│──│  crud.py  │  │
                                  │  └────┬─────┘  │  models.py│  │
                                  │       │        │  db.py    │  │
                                  │       ▼        └─────┬─────┘  │
                                  │  ┌───────────┐       │        │
                                  │  │intelligence│       ▼        │
                                  │  │ai_parser.py│  ┌─────────┐  │
                                  │  └─────┬──────┘  │PostgreSQL│  │
                                  │        │         │ (Docker) │  │
                                  └────────┼─────────┴──────────┘  │
                                           │                       
                                           ▼                       
                                  ┌──────────────────┐            
                                  │   Groq Cloud API  │            
                                  │  (Llama 4 Scout)  │            
                                  └──────────────────┘            
```

---

## 📂 Struktur Proyek

```
SFI/
├── backend/
│   ├── __init__.py
│   ├── bot.py                  # Entry point — Telegram Bot handlers
│   ├── database/
│   │   ├── __init__.py
│   │   ├── db.py               # Database engine & session
│   │   ├── models.py           # SQLAlchemy models (User, Inventory, ScanLog)
│   │   ├── crud.py             # CRUD operations
│   │   └── encryption.py       # Fernet encryption untuk Chat ID
│   └── intelligence/
│       ├── __init__.py
│       └── ai_parser.py        # Groq VLM integration (AI Scanner)
├── tests/
│   ├── __init__.py
│   └── test_core.py            # Unit tests
├── .env.example                # Template environment variables
├── docker-compose.yml          # PostgreSQL container
├── requirements.txt            # Python dependencies
├── DEPLOYMENT_RASPI.md         # Panduan deployment ke Raspberry Pi
├── SKPL SFI.md                 # Dokumen Spesifikasi Kebutuhan
└── README.md                   # ← Anda di sini
```

---

## 🚀 Quick Start

### Prasyarat

- **Python** 3.10+
- **Docker** & Docker Compose (untuk PostgreSQL)
- **Telegram Bot Token** (dari [@BotFather](https://t.me/BotFather))
- **Groq API Key** (dari [console.groq.com](https://console.groq.com))

### 1. Clone Repository

```bash
git clone <URL_REPO_SFI>
cd SFI
```

### 2. Setup Environment

```bash
# Buat virtual environment
python -m venv .venv

# Aktivasi (Windows)
.venv\Scripts\activate

# Aktivasi (Linux/macOS)
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Konfigurasi Environment Variables

```bash
cp .env.example .env
```

Edit file `.env` dan isi:

```env
# Database (SQLite untuk development, PostgreSQL untuk production)
DATABASE_URL="sqlite:///./sfi_database.db"

# Telegram Bot
TELEGRAM_BOT_TOKEN="token_dari_botfather"

# Groq API (untuk AI Scanner & NLQ)
GROQ_API_KEY="api_key_dari_groq"

# Encryption Key
# Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
ENCRYPTION_KEY="fernet_key_anda"
```

### 4. Jalankan Database (Opsional — untuk PostgreSQL)

```bash
docker compose up -d
```

> Untuk development cepat, gunakan SQLite (default di `.env.example`).

### 5. Jalankan Bot

```bash
python backend/bot.py
```

Bot akan berjalan dan siap menerima pesan di Telegram. 🎉

---

## 🤖 Perintah Bot

| Perintah | Deskripsi |
|---|---|
| `/start` | Mendaftar akun & melihat intro bot |
| `/help` | Menampilkan panduan penggunaan |
| `/isikulkas` | Melihat semua stok yang tersimpan |
| `/expired` | Cek barang yang mendekati kedaluwarsa (≤ 3 hari) |
| `/tambah [nama] [kategori] [jumlah] [satuan] [hari]` | Menambah barang manual |
| `/ambil [nama] [jumlah]` | Mengeluarkan barang dari kulkas |
| 📸 *Kirim Foto* | AI Scanner — otomatis check-in barang |
| 💬 *Ketik Pertanyaan* | Natural Language Query tentang isi kulkas |

**Contoh penggunaan:**
```
/tambah Susu Kemasan 2 kotak 7
/ambil Susu 1
"Apakah bayam saya masih segar?"
"Apa saja yang hampir expired?"
```

---

## 🛠️ Tech Stack

| Layer | Teknologi |
|---|---|
| **Bahasa** | Python 3.10+ |
| **Bot Framework** | python-telegram-bot v20+ |
| **Database** | PostgreSQL 15 (Docker) / SQLite (dev) |
| **ORM** | SQLAlchemy 2.0+ |
| **AI / LLM** | Groq API — Llama 4 Scout 17B (Vision) |
| **NLQ** | Groq API — Llama 3.3 70B Versatile |
| **Enkripsi** | cryptography (Fernet) |
| **Testing** | pytest |
| **Containerization** | Docker Compose |
| **Deployment Target** | Raspberry Pi 4B/5 |

---

## 🧪 Testing

```bash
# Jalankan semua test
pytest tests/ -v
```

---

## 🍓 Deployment (Raspberry Pi)

Untuk deployment ke perangkat edge (Raspberry Pi), lihat panduan lengkap di:

📄 **[DEPLOYMENT_RASPI.md](./DEPLOYMENT_RASPI.md)**

Mencakup: kebutuhan hardware, wiring, setup OS, systemd service, dan integrasi IP Camera.

---

## 👥 Tim Pengembang

| Nama | Peran |
|---|---|
| Rama Owarianto Putra Suharjito | Developer |
| Muhammad Kenas Galeno Putra | Developer |
| Dionisius Marcell Putra Indranto | Developer |
| Muhammad Hildan Adiwena | Developer |

**Institusi:** Jurusan Teknologi Informasi — Institut Teknologi Sepuluh Nopember (ITS)

---

## 📄 Dokumen Terkait

- [Spesifikasi Kebutuhan Perangkat Lunak (SKPL)](./SKPL%20SFI.md)
- [Panduan Deployment Raspberry Pi](./DEPLOYMENT_RASPI.md)

---

<p align="center">
  <i>Smart Fridge Inventory — Capstone Project 2026</i><br>
  <i>Jurusan Teknologi Informasi, Institut Teknologi Sepuluh Nopember</i>
</p>
