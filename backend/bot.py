import os
import sys
import logging
import tempfile
import datetime
import cv2
import asyncio
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
)
from dotenv import load_dotenv

load_dotenv()

# Menambahkan root directory ke sys.path agar bisa dijalankan langsung dari IDE
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database.db import SessionLocal
from backend.database import crud
from backend.database.models import CategoryEnum, ExpirySourceEnum, ActionEnum
from backend.intelligence.ai_parser import parse_fridge_item_image

# ========================================================
# 📸 FUNGSI AMBIL FOTO WEBCAM (OPEN-CLOSE MODE)
# Optimasi untuk Raspberry Pi 3 (1GB RAM):
# Kamera dibuka hanya saat capture, lalu langsung dilepas
# agar tidak menghabiskan RAM saat idle.
# ========================================================

async def capture_webcam(output_path="/tmp/fridge_capture.jpg") -> bool:
    """Capture an image from webcam using Open-Close Mode.
    Kamera dibuka saat dibutuhkan dan langsung dilepas setelah selesai
    untuk menghemat RAM pada perangkat dengan memori terbatas.
    """
    cap = None
    try:
        import numpy as np

        logging.info("📸 Membuka koneksi webcam...")
        # -1 biasanya mendeteksi kamera USB utama di Linux
        cap = cv2.VideoCapture(-1)

        if not cap.isOpened():
            logging.error("Webcam tidak terhubung atau tidak terdeteksi.")
            return False

        # Beri waktu awal agar sensor siap (warm-up)
        await asyncio.sleep(2)

        logging.info("Warming up camera sensor...")

        # Tarik 15 frame untuk memaksa sensor menyesuaikan cahaya
        # (dikurangi dari 30 untuk menghemat waktu & resource di Pi 3)
        for _ in range(15):
            cap.grab()  # grab() lebih cepat dari read()
            await asyncio.sleep(0.05)

        ret, frame = cap.read()

        # Validasi: Jika gambar masih nyaris hitam pekat, tarik frame tambahan
        if ret and np.mean(frame) < 10.0:
            logging.info("Gambar masih terlalu gelap, melakukan ekstra warm-up...")
            for _ in range(15):
                cap.read()
                await asyncio.sleep(0.1)
            ret, frame = cap.read()

        if ret:
            cv2.imwrite(output_path, frame)
            logging.info("📸 Foto berhasil diambil.")
            return True
        return False
    except Exception as e:
        logging.error(f"Gagal mengambil foto dari webcam: {e}")
        return False
    finally:
        # Selalu lepas resource kamera setelah selesai
        if cap is not None:
            cap.release()
            logging.info("📸 Koneksi webcam dilepas.")

async def _process_webcam_scan(update, context, mode="masuk"):
    """Fungsi internal untuk memproses scan webcam.
    mode='masuk' → check-in (tambah barang ke kulkas)
    mode='keluar' → check-out (kurangi/hapus barang dari kulkas)
    """
    chat_id = str(update.effective_chat.id)
    action_text = "memasukkan" if mode == "masuk" else "mengeluarkan"
    status_msg = await context.bot.send_message(
        chat_id=chat_id,
        text=f"📸 Memotret barang yang akan di{action_text[2:]}..."
    )

    img_path = "/tmp/fridge_capture.jpg"
    success = await capture_webcam(img_path)

    if not success:
        await context.bot.edit_message_text(
            chat_id=chat_id, message_id=status_msg.message_id,
            text="❌ Gagal memotret dari webcam. Pastikan kamera terpasang di Raspberry Pi."
        )
        return

    await context.bot.edit_message_text(
        chat_id=chat_id, message_id=status_msg.message_id,
        text="🤖 Memproses hasil foto kamera dengan AI..."
    )

    db = SessionLocal()
    try:
        user = crud.get_user_by_chat_id(db, chat_id)
        if not user:
            await context.bot.edit_message_text(
                chat_id=chat_id, message_id=status_msg.message_id,
                text="Kamu belum terdaftar, silahkan ketik /start."
            )
            return

        ai_results = parse_fridge_item_image(img_path)

        if not ai_results:
            await context.bot.edit_message_text(
                chat_id=chat_id, message_id=status_msg.message_id,
                text="❌ Tidak dapat mengenali barang dalam foto. Coba arahkan barang lebih dekat ke kamera."
            )
            return

        result_lines = []

        if mode == "masuk":
            result_lines = _process_checkin(db, user, ai_results)
        else:
            result_lines = _process_checkout(db, user, ai_results)

        count = len(result_lines)
        header = f"*Hasil Scan — {'MASUK' if mode == 'masuk' else 'KELUAR'} ({count} barang):*\n" if count > 1 else f"*Hasil Scan — {'MASUK' if mode == 'masuk' else 'KELUAR'}:*\n"
        body = "\n".join(result_lines)
        result_text = f"{header}{body}"

        with open(img_path, 'rb') as photo:
            await context.bot.send_photo(chat_id=chat_id, photo=photo, caption=result_text, parse_mode="Markdown")

        await context.bot.delete_message(chat_id=chat_id, message_id=status_msg.message_id)

    finally:
        db.close()


def _process_checkin(db, user, ai_results) -> list:
    """Proses check-in: tambahkan barang ke inventaris kulkas."""
    items_in_fridge = crud.get_active_inventory_by_user(db, user.user_id)
    result_lines = []

    for ai_result in ai_results:
        nama = ai_result.get("item_name", "Tidak diketahui")
        nama_lower = nama.lower()
        kategori_str = ai_result.get("category", "Lainnya")
        try:
            jumlah = int(ai_result.get("quantity", 1))
        except (ValueError, TypeError):
            jumlah = 1
        satuan = ai_result.get("unit", "buah")
        expiry_date_str = ai_result.get("expiry_date")
        freshness_condition = ai_result.get("freshness_condition")
        estimated_days = ai_result.get("estimated_days_to_expire")

        # Cek apakah barang sudah ada di kulkas
        match = next((i for i in items_in_fridge if i.item_name.lower() == nama_lower), None)
        if not match:
            match = next(
                (i for i in items_in_fridge if nama_lower in i.item_name.lower() or i.item_name.lower() in nama_lower),
                None,
            )

        if match:
            # Barang sudah ada → tambah kuantitas
            new_qty = match.quantity + jumlah
            crud.update_inventory_quantity(db, match.item_id, new_qty)
            crud.create_scan_log(db, match.item_id, ActionEnum.CHECKIN, jumlah)
            result_lines.append(f"📥 {match.item_name}: +{jumlah} {match.unit} (total: {new_qty})")
        else:
            # Barang baru → buat entry baru
            try:
                kategori = CategoryEnum(kategori_str.capitalize())
            except ValueError:
                kategori = CategoryEnum.LAINNYA

            expiry_date = None
            expiry_source = ExpirySourceEnum.OCR

            if expiry_date_str:
                try:
                    expiry_date = datetime.datetime.strptime(expiry_date_str, "%Y-%m-%d").date()
                except ValueError:
                    expiry_date = None

            if not expiry_date:
                expiry_source = ExpirySourceEnum.LLM_ESTIMATE
                if estimated_days is not None:
                    try:
                        expiry_date = datetime.date.today() + datetime.timedelta(days=int(estimated_days))
                    except (ValueError, TypeError):
                        pass

            if not expiry_date:
                fallback_days = {
                    CategoryEnum.KEMASAN: 180,
                    CategoryEnum.SAYUR: 5,
                    CategoryEnum.BUAH: 7,
                    CategoryEnum.DAGING: 3,
                    CategoryEnum.LAINNYA: 14,
                }
                days = fallback_days.get(kategori, 14)
                expiry_date = datetime.date.today() + datetime.timedelta(days=days)
                expiry_source = ExpirySourceEnum.LLM_ESTIMATE

            item_data = {
                "user_id": int(str(user.user_id)),
                "item_name": nama,
                "category": kategori,
                "unit": satuan,
                "quantity": jumlah,
                "expiry_date": expiry_date,
                "expiry_source": expiry_source,
            }

            new_item = crud.create_inventory_item(db, item_data)
            crud.create_scan_log(db, int(str(new_item.item_id)), ActionEnum.CHECKIN, jumlah)

            exp_text = str(expiry_date)
            if expiry_source == ExpirySourceEnum.LLM_ESTIMATE:
                if freshness_condition:
                    exp_text += f" (prediksi, kondisi: {freshness_condition})"
                else:
                    exp_text += " (prediksi)"

            result_lines.append(f"📥 {nama} ({kategori.value}), {jumlah} {satuan}, exp: {exp_text}")

    return result_lines


def _process_checkout(db, user, ai_results) -> list:
    """Proses check-out: kurangi barang dari inventaris kulkas."""
    items_in_fridge = crud.get_active_inventory_by_user(db, user.user_id)
    result_lines = []

    for ai_result in ai_results:
        nama = ai_result.get("item_name", "Tidak diketahui")
        nama_lower = nama.lower()
        try:
            jumlah = int(ai_result.get("quantity", 1))
        except (ValueError, TypeError):
            jumlah = 1

        # Cari barang di inventaris
        match = next((i for i in items_in_fridge if i.item_name.lower() == nama_lower), None)
        if not match:
            match = next(
                (i for i in items_in_fridge if nama_lower in i.item_name.lower() or i.item_name.lower() in nama_lower),
                None,
            )

        if match:
            new_qty = max(0, match.quantity - jumlah)
            crud.update_inventory_quantity(db, match.item_id, new_qty)
            action = ActionEnum.CHECKOUT if new_qty == 0 else ActionEnum.PARTIAL_CHECKOUT
            crud.create_scan_log(db, match.item_id, action, -jumlah)
            if new_qty == 0:
                result_lines.append(f"📤 {match.item_name}: dikeluarkan semua ({jumlah} {match.unit})")
            else:
                result_lines.append(f"📤 {match.item_name}: -{jumlah} {match.unit} (sisa: {new_qty})")
        else:
            result_lines.append(f"⚠️ {nama}: tidak ditemukan di kulkas, dilewati")

    return result_lines


async def masuk_scan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command /masuk — Tunjukkan barang ke kamera untuk MEMASUKKAN ke kulkas."""
    await _process_webcam_scan(update, context, mode="masuk")


async def keluar_scan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command /keluar — Tunjukkan barang ke kamera untuk MENGELUARKAN dari kulkas."""
    await _process_webcam_scan(update, context, mode="keluar")


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /start. Mendaftarkan user ke database jika belum ada."""
    chat_id = str(update.effective_chat.id)  # type: ignore
    username = update.effective_user.username  # type: ignore

    db = SessionLocal()
    try:
        user = crud.get_user_by_chat_id(db, chat_id)
        if not user:
            user = crud.create_user(db, chat_id, username)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,  # type: ignore
            text=f"Halo, {username or 'pengguna'}. Selamat datang di *SFI Bot* (Smart Fridge Inventory).\n\n"
            "Bot ini membantu Anda mencatat isi kulkas agar tidak ada makanan yang terbuang.\n\n"
            "*Mulai dari sini:*\n"
            "- `/tambah` untuk mencatat barang baru\n"
            "- `/isikulkas` untuk melihat semua stok\n"
            "- `/expired` untuk cek barang hampir kedaluwarsa\n\n"
            "Ketik /help untuk panduan lengkap.",
            parse_mode="Markdown",
        )
    finally:
        db.close()


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /help. Menampilkan panduan penggunaan bot."""
    help_text = (
        "*Panduan SFI Bot*\n\n"
        "*📸 Kamera Webcam (Raspberry Pi):*\n"
        "`/masuk` — Tunjukkan barang ke kamera → *masuk* ke kulkas\n"
        "`/keluar` — Tunjukkan barang ke kamera → *keluar* dari kulkas\n\n"
        "*📋 Perintah Manual:*\n"
        "`/tambah [nama] [kategori] [jumlah] [satuan] [hari]`\n"
        "  Contoh: `/tambah Susu Kemasan 2 botol 7`\n"
        "`/ambil [nama] [jumlah]`\n"
        "  Contoh: `/ambil Susu 1`\n\n"
        "*📊 Lihat Data:*\n"
        "`/isikulkas` — Lihat semua stok di kulkas\n"
        "`/expired` — Cek barang hampir kedaluwarsa\n\n"
        "*📷 Kirim Foto via Telegram:*\n"
        "Kirim foto barang → otomatis *masuk* ke kulkas\n"
        "Kirim foto + caption `keluar` → *keluar* dari kulkas\n\n"
        "*💬 Tanya Jawab:*\n"
        "Ketik pertanyaan apapun tentang isi kulkas secara natural.\n"
        'Contoh: "Apa saja yang hampir expired?"\n\n'
        "*🔔 Notifikasi:*\n"
        "Bot mengirim peringatan otomatis setiap pagi (08:00 WIB) "
        "jika ada barang mendekati kedaluwarsa.\n\n"
        "`/start` — Daftar akun\n"
        "`/help` — Tampilkan panduan ini"
    )
    await context.bot.send_message(
        chat_id=update.effective_chat.id,  # type: ignore
        text=help_text,
        parse_mode="Markdown",
    )


async def isikulkas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /isikulkas. Menampilkan semua barang yang ada di kulkas user."""
    chat_id = str(update.effective_chat.id)  # type: ignore
    db = SessionLocal()
    try:
        user = crud.get_user_by_chat_id(db, chat_id)
        if not user:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,  # type: ignore
                text="Kamu belum terdaftar, silahkan ketik /start.",
            )
            return

        items = crud.get_active_inventory_by_user(db, user.user_id)  # type: ignore
        if not items:
            await context.bot.send_message(
                chat_id=update.effective_chat.id, text="Kulkas kosong."  # type: ignore
            )
            return

        response = "*Isi Kulkas:*\n\n"
        for item in items:
            response += f"- *{item.item_name}* ({item.category.value}): {item.quantity} {item.unit} (Exp: {item.expiry_date})\n"

        await context.bot.send_message(
            chat_id=update.effective_chat.id, text=response, parse_mode="Markdown"  # type: ignore
        )
    finally:
        db.close()


async def expired(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /expired. Menampilkan barang yang akan kedaluwarsa (<= 3 hari)."""
    chat_id = str(update.effective_chat.id)  # type: ignore
    db = SessionLocal()
    try:
        user = crud.get_user_by_chat_id(db, chat_id)
        if not user:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="Kamu belum terdaftar, silahkan ketik /start.")  # type: ignore
            return

        # Ambil item yang expired dalam 3 hari
        items = crud.get_expiring_items(db, days_threshold=3)
        # Filter hanya milik user ini
        user_items = [i for i in items if i.user_id == user.user_id]

        if not user_items:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="Tidak ada barang yang mendekati kedaluwarsa dalam 3 hari ke depan.")  # type: ignore
            return

        response = "*Barang Mendekati Kedaluwarsa:*\n\n"
        for item in user_items:
            response += f"- *{item.item_name}*: sisa {item.quantity} {item.unit} (Exp: {item.expiry_date})\n"

        await context.bot.send_message(chat_id=update.effective_chat.id, text=response, parse_mode="Markdown")  # type: ignore
    finally:
        db.close()


async def tambah(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /tambah. Format: /tambah [nama] [kategori] [jumlah] [satuan] [hari_sebelum_expired]"""
    chat_id = str(update.effective_chat.id)  # type: ignore
    args = context.args

    if len(args) < 5:  # type: ignore
        await context.bot.send_message(
            chat_id=update.effective_chat.id,  # type: ignore
            text="Format salah! Gunakan:\n`/tambah [nama] [kategori] [jumlah] [satuan] [hari_sebelum_expired]`\n"
            "Contoh: `/tambah Susu Kemasan 1 kotak 7`\n\n"
            "Kategori: Sayur, Buah, Daging, Kemasan, Lainnya",
            parse_mode="Markdown",
        )
        return

    nama = args[0]  # type: ignore
    kategori_str = args[1].capitalize()  # type: ignore
    try:
        jumlah = int(args[2])  # type: ignore
        satuan = args[3]  # type: ignore
        hari_expired = int(args[4])  # type: ignore
    except ValueError:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Jumlah dan hari_sebelum_expired harus berupa angka!")  # type: ignore
        return

    try:
        kategori = CategoryEnum(kategori_str)
    except ValueError:
        kategori = CategoryEnum.LAINNYA

    expiry_date = datetime.date.today() + datetime.timedelta(days=hari_expired)

    db = SessionLocal()
    try:
        user = crud.get_user_by_chat_id(db, chat_id)
        if not user:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="Kamu belum terdaftar, silahkan ketik /start.")  # type: ignore
            return

        item_data = {
            "user_id": user.user_id,
            "item_name": nama,
            "category": kategori,
            "unit": satuan,
            "quantity": jumlah,
            "expiry_date": expiry_date,
            "expiry_source": ExpirySourceEnum.MANUAL,
        }
        new_item = crud.create_inventory_item(db, item_data)
        crud.create_scan_log(db, new_item.item_id, ActionEnum.CHECKIN, jumlah)  # type: ignore

        await context.bot.send_message(
            chat_id=update.effective_chat.id,  # type: ignore
            text=f"Ditambahkan: {jumlah} {satuan} *{nama}* (exp: {expiry_date}).",
            parse_mode="Markdown",
        )
    finally:
        db.close()


async def ambil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /ambil. Format: /ambil [nama_barang] [jumlah]"""
    chat_id = str(update.effective_chat.id)  # type: ignore
    args = context.args

    if len(args) < 2:  # type: ignore
        await context.bot.send_message(
            chat_id=update.effective_chat.id,  # type: ignore
            text="Format salah! Gunakan:\n`/ambil [nama_barang] [jumlah]`\nContoh: `/ambil Susu 1`",
            parse_mode="Markdown",
        )
        return

    nama_barang = args[0].lower()  # type: ignore
    try:
        jumlah_ambil = int(args[1])  # type: ignore
    except ValueError:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Jumlah harus berupa angka!")  # type: ignore
        return

    db = SessionLocal()
    try:
        user = crud.get_user_by_chat_id(db, chat_id)
        if not user:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="Kamu belum terdaftar, silahkan ketik /start.")  # type: ignore
            return

        items = crud.get_active_inventory_by_user(db, user.user_id)  # type: ignore
        target_item = next(
            (item for item in items if item.item_name.lower() == nama_barang), None
        )

        if not target_item:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Barang *{nama_barang}* tidak ditemukan di kulkas!", parse_mode="Markdown")  # type: ignore
            return

        if jumlah_ambil > target_item.quantity:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Stok tidak cukup! Sisa *{target_item.item_name}* hanya {target_item.quantity} {target_item.unit}.", parse_mode="Markdown")  # type: ignore
            return

        new_quantity = target_item.quantity - jumlah_ambil
        crud.update_inventory_quantity(db, target_item.item_id, new_quantity)  # type: ignore

        action = (
            ActionEnum.CHECKOUT if new_quantity == 0 else ActionEnum.PARTIAL_CHECKOUT
        )
        crud.create_scan_log(db, target_item.item_id, action, -jumlah_ambil)  # type: ignore

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"Diambil: {jumlah_ambil} {target_item.unit} *{target_item.item_name}*. Sisa: {new_quantity}.",
            parse_mode="Markdown",
        )  # type: ignore
    finally:
        db.close()


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler foto via Telegram.
    Default = CHECK-IN (masuk ke kulkas).
    Jika caption mengandung 'keluar' atau 'ambil' = CHECK-OUT (keluar dari kulkas).
    """
    if not update.effective_chat or not update.message or not update.message.photo:
        return
    chat_id = str(update.effective_chat.id)

    # Cek caption untuk menentukan mode (masuk/keluar)
    caption = (update.message.caption or "").strip().lower()
    checkout_keywords = ["keluar", "ambil", "keluarkan", "checkout", "check-out"]
    is_checkout = any(keyword in caption for keyword in checkout_keywords)
    mode_text = "KELUAR" if is_checkout else "MASUK"

    status_msg = await context.bot.send_message(
        chat_id=chat_id,
        text=f"📷 Memproses gambar (mode: {mode_text})...",
    )

    try:
        photo_file = await update.message.photo[-1].get_file()

        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp_file:
            img_path = tmp_file.name

        await photo_file.download_to_drive(custom_path=img_path)

        ai_results = parse_fridge_item_image(img_path)

        os.remove(img_path)

        if not ai_results:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=status_msg.message_id,
                text="Tidak dapat mengenali barang dalam gambar ini.",
            )
            return

        db = SessionLocal()
        try:
            user = crud.get_user_by_chat_id(db, chat_id)
            if not user:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=status_msg.message_id,
                    text="Kamu belum terdaftar, silahkan ketik /start.",
                )
                return

            if is_checkout:
                result_lines = _process_checkout(db, user, ai_results)
            else:
                result_lines = _process_checkin(db, user, ai_results)

            count = len(result_lines)
            header = f"*Hasil Scan — {mode_text} ({count} barang):*\n" if count > 1 else f"*Hasil Scan — {mode_text}:*\n"
            body = "\n".join(result_lines)
            success_text = f"{header}{body}"

            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=status_msg.message_id,
                text=success_text,
                parse_mode="Markdown",
            )

        finally:
            db.close()

    except Exception as e:
        logging.error(f"Gagal memproses gambar: {e}")
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=status_msg.message_id,
            text="Tidak dapat memproses gambar ini. Coba kirim ulang dengan"
            " pencahayaan yang lebih baik atau sudut yang berbeda.",
        )


async def natural_language_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk Natural Language Query (SKPL-F13).
    User bisa bertanya tentang isi kulkas secara natural."""
    if not update.effective_chat or not update.message:
        return
    chat_id = str(update.effective_chat.id)
    user_question = update.message.text

    db = SessionLocal()
    try:
        user = crud.get_user_by_chat_id(db, chat_id)
        if not user:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Kamu belum terdaftar, silahkan ketik /start.",
            )
            return

        # Ambil data kulkas user untuk konteks AI
        items = crud.get_active_inventory_by_user(db, user.user_id)  # type: ignore
        inventory_text = "Kulkas kosong."
        if items:
            lines = []
            for item in items:
                lines.append(
                    f"- {item.item_name} ({item.category.value}): "
                    f"{item.quantity} {item.unit}, exp: {item.expiry_date}"
                )
            inventory_text = "\n".join(lines)

        # Kirim ke Groq untuk diproses
        from groq import Groq

        groq_key = os.environ.get("GROQ_API_KEY")
        if not groq_key:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Fitur AI belum dikonfigurasi. Silakan hubungi admin.",
            )
            return

        client = Groq(api_key=groq_key)
        today = datetime.date.today().isoformat()

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"Kamu adalah asisten Smart Fridge Inventory. "
                        f"Tanggal hari ini: {today}. "
                        f"Berikut isi kulkas user saat ini:\n{inventory_text}\n\n"
                        f"Jawab pertanyaan user secara ringkas dan informatif dalam Bahasa Indonesia. "
                        f"Jika user bertanya di luar topik kulkas, arahkan kembali dengan sopan."
                    ),
                },
                {"role": "user", "content": user_question},
            ],
            temperature=0.3,
            max_completion_tokens=512,
        )

        ai_answer = response.choices[0].message.content
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"{ai_answer}",
        )

    except Exception as e:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"Maaf, terjadi kesalahan saat memproses pertanyaan Anda: {str(e)}",
        )
    finally:
        db.close()


async def send_daily_notifications(context: ContextTypes.DEFAULT_TYPE):
    """Job terjadwal: mengirim notifikasi harian untuk barang mendekati expired (SKPL-F10)."""
    db = SessionLocal()
    try:
        users = crud.get_all_users(db)
        for user in users:
            items = crud.get_expiring_items(db, days_threshold=3)
            user_items = [i for i in items if i.user_id == user.user_id]

            if not user_items:
                continue

            response = "*Peringatan — Barang mendekati kedaluwarsa:*\n\n"
            for item in user_items:
                days_left = (item.expiry_date - datetime.date.today()).days
                if days_left < 0:
                    status = f"SUDAH EXPIRED sejak {item.expiry_date}"
                elif days_left == 0:
                    status = f"expired hari ini ({item.expiry_date})"
                elif days_left == 1:
                    status = f"besok expired ({item.expiry_date})"
                else:
                    status = f"{days_left} hari lagi ({item.expiry_date})"

                response += (
                    f"- *{item.item_name}*: {item.quantity} {item.unit} "
                    f"({status})\n"
                )

            response += "\nSegera konsumsi atau olah agar tidak terbuang."

            try:
                decrypted_id = crud.get_decrypted_chat_id(user)
                await context.bot.send_message(
                    chat_id=int(decrypted_id),
                    text=response,
                    parse_mode="Markdown",
                )
            except Exception as e:
                logging.error(f"Gagal kirim notifikasi ke {user.telegram_chat_id}: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    if not BOT_TOKEN:
        print(
            "ERROR: TELEGRAM_BOT_TOKEN belum diatur di environment variable atau file .env"
        )
        exit(1)

    # Inisialisasi database (membuat tabel jika belum ada)
    from backend.database.db import init_db
    init_db()

    # Kamera diinisialisasi secara on-demand (Open-Close Mode)
    # untuk menghemat RAM pada Raspberry Pi 3

    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # Command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("isikulkas", isikulkas))
    application.add_handler(CommandHandler("expired", expired))
    application.add_handler(CommandHandler("tambah", tambah))
    application.add_handler(CommandHandler("ambil", ambil))
    application.add_handler(CommandHandler("masuk", masuk_scan_command))
    application.add_handler(CommandHandler("keluar", keluar_scan_command))

    # Photo handler (AI Scanner)
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    # Natural Language Query handler (fallback untuk teks biasa)
    application.add_handler(
        MessageHandler(filters.TEXT & (~filters.COMMAND), natural_language_query)
    )

    # Notifikasi harian terjadwal setiap jam 08:00 WIB (UTC+7 = 01:00 UTC)
    job_queue = application.job_queue
    if job_queue:
        job_queue.run_daily(
            send_daily_notifications,
            time=datetime.time(hour=1, minute=0, second=0),  # 08:00 WIB
            name="daily_expiry_notification",
        )
        print("Notifikasi harian terjadwal setiap jam 08:00 WIB.")
        
        # Auto-scan dihapus: kamera hanya aktif saat user
        # menjalankan /masuk, /keluar, atau mengirim foto

    print("Bot SFI sedang berjalan. Tekan Ctrl+C untuk berhenti.")
    application.run_polling()
