import os
import sys
import logging
import tempfile
import datetime
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
        "*Perintah:*\n"
        "`/start` — Daftar akun\n"
        "`/isikulkas` — Lihat semua stok\n"
        "`/expired` — Cek barang hampir kedaluwarsa\n"
        "`/tambah [nama] [kategori] [jumlah] [satuan] [hari]`\n"
        "  Contoh: `/tambah Susu Kemasan 2 botol 7`\n"
        "`/ambil [nama] [jumlah]`\n"
        "  Contoh: `/ambil Susu 1`\n"
        "`/help` — Tampilkan panduan ini\n\n"
        "*AI Scanner:*\n"
        "Kirim foto barang ke chat ini. Sistem otomatis mendeteksi:\n"
        "- Barang baru → masuk ke kulkas (check-in)\n"
        "- Barang sudah ada → diambil dari kulkas (check-out)\n\n"
        "*Tanya Jawab:*\n"
        "Ketik pertanyaan apapun tentang isi kulkas secara natural.\n"
        'Contoh: "Apa saja yang hampir expired?"\n\n'
        "*Notifikasi:*\n"
        "Bot mengirim peringatan otomatis setiap pagi (08:00 WIB) "
        "jika ada barang mendekati kedaluwarsa."
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
    """Handler foto — selalu CHECK-IN.
    Jika barang sudah ada di kulkas, stok akan ditambahkan.
    Check-out dilakukan otomatis via /ambil atau sensor pintu.
    """
    if not update.effective_chat or not update.message or not update.message.photo:
        return
    chat_id = str(update.effective_chat.id)

    status_msg = await context.bot.send_message(
        chat_id=chat_id,
        text="Memproses gambar...",
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

            items_in_fridge = crud.get_active_inventory_by_user(
                db, user.user_id  # type: ignore
            )

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
                match = next(
                    (i for i in items_in_fridge if i.item_name.lower() == nama_lower),
                    None,
                )
                if not match:
                    match = next(
                        (
                            i
                            for i in items_in_fridge
                            if nama_lower in i.item_name.lower()
                            or i.item_name.lower() in nama_lower
                        ),
                        None,
                    )

                if match:
                    # Barang sudah ada → tambah kuantitas
                    new_qty = match.quantity + jumlah
                    crud.update_inventory_quantity(
                        db, match.item_id, new_qty  # type: ignore
                    )
                    crud.create_scan_log(
                        db, match.item_id, ActionEnum.CHECKIN, jumlah  # type: ignore
                    )
                    result_lines.append(
                        f"- {match.item_name}: +{jumlah} {match.unit}"
                        f" (total: {new_qty})"
                    )
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
                            expiry_date = datetime.datetime.strptime(
                                expiry_date_str, "%Y-%m-%d"
                            ).date()
                        except ValueError:
                            expiry_date = None

                    if not expiry_date:
                        expiry_source = ExpirySourceEnum.LLM_ESTIMATE
                        if estimated_days is not None:
                            try:
                                expiry_date = (
                                    datetime.date.today()
                                    + datetime.timedelta(days=int(estimated_days))
                                )
                            except (ValueError, TypeError):
                                pass

                    if not expiry_date:
                        expiry_date = datetime.date.today() + datetime.timedelta(days=7)
                        expiry_source = ExpirySourceEnum.LLM_ESTIMATE

                    item_data = {
                        "user_id": int(str(user.user_id)),  # type: ignore
                        "item_name": nama,
                        "category": kategori,
                        "unit": satuan,
                        "quantity": jumlah,
                        "expiry_date": expiry_date,
                        "expiry_source": expiry_source,
                    }

                    new_item = crud.create_inventory_item(db, item_data)
                    crud.create_scan_log(
                        db,
                        int(str(new_item.item_id)),  # type: ignore
                        ActionEnum.CHECKIN,
                        jumlah,
                    )

                    exp_text = str(expiry_date)
                    if expiry_source == ExpirySourceEnum.LLM_ESTIMATE:
                        if freshness_condition:
                            exp_text += f" (prediksi, kondisi: {freshness_condition})"
                        else:
                            exp_text += " (prediksi)"

                    result_lines.append(
                        f"- {nama} ({kategori.value}), {jumlah} {satuan},"
                        f" exp: {exp_text}"
                    )

            count = len(result_lines)
            header = (
                f"*Hasil scan ({count} barang):*\n" if count > 1 else "*Hasil scan:*\n"
            )
            body = "\n".join(result_lines)
            success_text = f"{header}{body}\n\nSudah ditambahkan ke kulkas."

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

    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # Command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("isikulkas", isikulkas))
    application.add_handler(CommandHandler("expired", expired))
    application.add_handler(CommandHandler("tambah", tambah))
    application.add_handler(CommandHandler("ambil", ambil))

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

    print("Bot SFI sedang berjalan. Tekan Ctrl+C untuk berhenti.")
    application.run_polling()
