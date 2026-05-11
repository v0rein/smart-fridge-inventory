"""
Modul enkripsi/dekripsi untuk data sensitif pengguna (SKPL-NF04).
Menggunakan Fernet symmetric encryption.
"""

import os
from cryptography.fernet import Fernet


def _get_cipher():
    """Mendapatkan Fernet cipher dari environment variable."""
    key = os.environ.get("ENCRYPTION_KEY")
    if not key:
        # Generate key baru jika belum ada (untuk development)
        key = Fernet.generate_key().decode()
        os.environ["ENCRYPTION_KEY"] = key
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt(plaintext: str) -> str:
    """Mengenkripsi string menjadi ciphertext."""
    cipher = _get_cipher()
    return cipher.encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """Mendekripsi ciphertext kembali menjadi string asli."""
    cipher = _get_cipher()
    return cipher.decrypt(ciphertext.encode()).decode()
