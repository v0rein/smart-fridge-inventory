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

        prompt = """
Kamu adalah sistem AI untuk Smart Fridge Inventory.
Tugasmu adalah menganalisis gambar produk/barang belanjaan.

Jika ada LEBIH DARI SATU barang dalam gambar, deteksi SEMUA barang.

Kembalikan HANYA JSON valid dengan format:
{
    "items": [
        {
            "item_name": "string",
            "category": "Sayur | Buah | Daging | Kemasan | Lainnya",
            "quantity": integer,
            "unit": "string",
            "expiry_date": "YYYY-MM-DD atau null",
            "freshness_condition": "string singkat atau null",
            "estimated_days_to_expire": integer atau null
        }
    ]
}

Aturan:
1. Jangan tambahkan teks apapun selain JSON murni.
2. Jika produk memiliki tanggal kedaluwarsa tercetak, isi expiry_date
   dengan format YYYY-MM-DD, lalu set estimated_days_to_expire
   dan freshness_condition ke null.
3. Jika produk TIDAK ADA tanggal kedaluwarsa (misal sayur/buah segar):
   - Set expiry_date ke null.
   - Isi freshness_condition berdasarkan analisis visual.
   - Isi estimated_days_to_expire dengan rata-rata umur simpan
     di kulkas (misal apel: 14, bayam: 5, daging: 3).
4. Quantity harus angka bulat.
5. Selalu kembalikan dalam format {"items": [...]}, bahkan untuk 1 barang.
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
            temperature=0.2,
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
