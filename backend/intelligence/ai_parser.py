import os
import json
import base64
import logging
from typing import Dict, Any, List
from groq import Groq


def get_client():
    """Inisialisasi Groq client."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY belum diatur di environment variable")
    return Groq(api_key=api_key)


def parse_fridge_item_image(image_path: str) -> List[Dict[str, Any]]:
    """
    Menganalisis gambar barang menggunakan Groq VLM (Llama 4 Scout).
    Mendukung deteksi multi-item dalam satu foto.
    Mengembalikan LIST of dictionaries, masing-masing berisi:
    item_name, category, quantity, unit, expiry_date,
    freshness_condition, estimated_days_to_expire
    """
    try:
        client = get_client()

        with open(image_path, "rb") as f:
            image_bytes = f.read()
        base64_image = base64.b64encode(image_bytes).decode("utf-8")

        # Sertakan tanggal hari ini agar AI bisa menghitung estimasi relatif
        from datetime import date
        today_str = date.today().isoformat()

        prompt = f"""
Kamu adalah sistem AI untuk Smart Fridge Inventory.
Tanggal hari ini adalah: {today_str}

Tugasmu adalah menganalisis gambar produk/barang belanjaan dengan SANGAT TELITI.

Jika ada LEBIH DARI SATU barang dalam gambar, deteksi SEMUA barang.

Kembalikan HANYA JSON valid dengan format:
{{
    "items": [
        {{
            "item_name": "string",
            "category": "Sayur | Buah | Daging | Kemasan | Lainnya",
            "quantity": integer,
            "unit": "string",
            "expiry_date": "YYYY-MM-DD atau null",
            "freshness_condition": "string singkat atau null",
            "estimated_days_to_expire": integer atau null
        }}
    ]
}}

ATURAN PENTING — IKUTI DENGAN KETAT:

1. IDENTIFIKASI NAMA BARANG:
   - WAJIB baca teks, label, merek, atau nama produk yang terlihat pada kemasan.
   - Gunakan nama merek + jenis produk jika terlihat (contoh: "Yupi Gummy", "Kapal Api Bubuk Kopi", "Indomie Goreng").
   - JANGAN PERNAH menjawab "Tidak diketahui" jika ada petunjuk visual apapun tentang jenis barang.
   - Jika merek tidak terbaca tapi jenis barang terlihat, tetap isi nama jenisnya (misal: "Permen Gummy", "Bubuk Kopi").

2. MEMBACA TANGGAL KEDALUWARSA (OCR) — PRIORITAS UTAMA:
   - Untuk produk KEMASAN, tanggal kedaluwarsa PASTI ADA di kemasan. Cari dengan sangat teliti.
   - Cari teks seperti: "EXP", "EXP DATE", "BEST BEFORE", "BB", "BAIK DIGUNAKAN SEBELUM",
     "GUNAKAN SEBELUM", "USE BY", "SELL BY", atau tanggal yang berdiri sendiri pada kemasan.
   - Format tanggal yang umum di Indonesia: DD/MM/YYYY, DD-MM-YYYY, MM/YYYY, DD MMM YYYY,
     atau bisa juga hanya bulan dan tahun (misal "MAR 2028", "03/2028").
   - Jika hanya ada bulan dan tahun (misal "MAR 2028"), gunakan tanggal 1 bulan tersebut
     (contoh: "2028-03-01").
   - Jika kamu berhasil membaca tanggal, isi expiry_date dalam format YYYY-MM-DD,
     lalu set estimated_days_to_expire dan freshness_condition ke null.

3. JIKA TANGGAL TIDAK TERBACA (gunakan estimasi realistis):
   - Untuk produk KEMASAN (snack, minuman kemasan, kopi bubuk, mie instan, dll):
     * estimated_days_to_expire harus REALISTIS: biasanya 180 sampai 730 hari (6 bulan - 2 tahun).
     * Snack kemasan (keripik, permen, gummy): 180-365 hari
     * Minuman kemasan (susu UHT, jus kotak): 90-365 hari
     * Kopi bubuk/instan: 365-730 hari
     * Mie instan: 180-270 hari
     * Makanan kaleng: 730-1095 hari
     * JANGAN PERNAH memprediksi produk kemasan hanya 7 hari.
   - Untuk produk SEGAR (tanpa kemasan):
     * Sayur hijau (bayam, kangkung): 3-5 hari
     * Sayur keras (wortel, kentang): 14-30 hari
     * Buah tropis (pisang, pepaya): 3-7 hari
     * Buah keras (apel, jeruk): 14-30 hari
     * Daging segar: 2-3 hari
     * Daging beku: 30-90 hari
     * Telur: 21-28 hari
     * Susu segar: 5-7 hari
   - Set expiry_date ke null.
   - Isi freshness_condition berdasarkan analisis visual.
   - Isi estimated_days_to_expire dengan estimasi realistis sesuai panduan di atas.

4. Quantity harus angka bulat.
5. Selalu kembalikan dalam format {{"items": [...]}}, bahkan untuk 1 barang.
6. Jangan tambahkan teks apapun selain JSON murni.
"""

        response = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}",
                            },
                        },
                        {
                            "type": "text",
                            "text": prompt,
                        },
                    ],
                }
            ],
            temperature=0.1,
            max_completion_tokens=2048,
            response_format={"type": "json_object"},
        )

        result_text = response.choices[0].message.content
        parsed = json.loads(result_text)  # type: ignore

        # Normalisasi: pastikan selalu mengembalikan list
        if isinstance(parsed, list):
            return parsed
        elif isinstance(parsed, dict):
            if "items" in parsed:
                return parsed["items"]
            else:
                return [parsed]
        else:
            return []

    except Exception as e:
        logging.error(f"Error in AI Parsing: {e}")
        raise e
