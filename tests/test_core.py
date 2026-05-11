"""
Unit tests untuk modul database CRUD dan enkripsi.
Jalankan: python -m pytest tests/ -v
"""

import os
import sys
import pytest
from datetime import date, timedelta
from unittest.mock import patch, MagicMock

# Setup path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database.models import (
    Base,
    CategoryEnum,
    ExpirySourceEnum,
    StatusEnum,
    ActionEnum,
)
from backend.database import crud
from backend.database.encryption import encrypt, decrypt

# --- Fixtures ---


@pytest.fixture
def db_session():
    """Membuat database SQLite in-memory untuk testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture(autouse=True)
def set_encryption_key():
    """Set encryption key untuk testing."""
    os.environ["ENCRYPTION_KEY"] = (
        "dGVzdGluZ19rZXlfMTIzNDU2Nzg5MDEyMzQ1Njc4OTAxMjM0NTY3ODkwMTI="
    )
    # Generate a proper Fernet key
    from cryptography.fernet import Fernet

    key = Fernet.generate_key().decode()
    os.environ["ENCRYPTION_KEY"] = key
    yield
    if "ENCRYPTION_KEY" in os.environ:
        del os.environ["ENCRYPTION_KEY"]


# --- Test Encryption ---


class TestEncryption:
    def test_encrypt_decrypt_roundtrip(self):
        """Data harus bisa dienkripsi dan didekripsi kembali."""
        original = "123456789"
        encrypted = encrypt(original)
        assert encrypted != original
        assert decrypt(encrypted) == original

    def test_encrypted_output_is_different(self):
        """Dua enkripsi dari teks yang sama menghasilkan ciphertext berbeda (nonce)."""
        text = "test_chat_id"
        enc1 = encrypt(text)
        enc2 = encrypt(text)
        assert enc1 != enc2  # Fernet uses unique IV each time

    def test_decrypt_invalid_raises(self):
        """Dekripsi data invalid harus raise exception."""
        with pytest.raises(Exception):
            decrypt("invalid_ciphertext")


# --- Test User CRUD ---


class TestUserCRUD:
    def test_create_user(self, db_session):
        """User baru harus tersimpan dengan chat_id terenkripsi."""
        user = crud.create_user(db_session, "12345", "testuser")
        assert user.username == "testuser"
        assert user.user_id is not None
        # Chat ID harus terenkripsi (bukan plaintext)
        assert str(user.telegram_chat_id) != "12345"

    def test_get_user_by_chat_id(self, db_session):
        """User harus bisa ditemukan dengan chat_id asli (plaintext)."""
        crud.create_user(db_session, "99999", "findme")
        found = crud.get_user_by_chat_id(db_session, "99999")
        assert found is not None
        assert found.username == "findme"

    def test_get_user_not_found(self, db_session):
        """User yang tidak ada harus mengembalikan None."""
        result = crud.get_user_by_chat_id(db_session, "nonexistent")
        assert result is None

    def test_get_all_users(self, db_session):
        """get_all_users harus mengembalikan semua user."""
        crud.create_user(db_session, "111", "a")
        crud.create_user(db_session, "222", "b")
        users = crud.get_all_users(db_session)
        assert len(users) == 2

    def test_get_decrypted_chat_id(self, db_session):
        """Chat ID harus bisa didekripsi kembali."""
        user = crud.create_user(db_session, "54321", "decrypttest")
        decrypted = crud.get_decrypted_chat_id(user)
        assert decrypted == "54321"


# --- Test Inventory CRUD ---


class TestInventoryCRUD:
    def _create_user_and_item(self, db_session, chat_id="100", days_to_expire=7):
        user = crud.create_user(db_session, chat_id, "tester")
        item_data = {
            "user_id": user.user_id,
            "item_name": "Susu",
            "category": CategoryEnum.KEMASAN,
            "unit": "kotak",
            "quantity": 3,
            "expiry_date": date.today() + timedelta(days=days_to_expire),
            "expiry_source": ExpirySourceEnum.MANUAL,
        }
        item = crud.create_inventory_item(db_session, item_data)
        return user, item

    def test_create_inventory_item(self, db_session):
        """Item baru harus tersimpan dengan status STORED."""
        _, item = self._create_user_and_item(db_session)
        assert item.item_name == "Susu"
        assert item.quantity == 3
        assert item.status == StatusEnum.STORED

    def test_get_active_inventory(self, db_session):
        """Hanya item dengan status STORED yang dikembalikan."""
        user, item = self._create_user_and_item(db_session)
        items = crud.get_active_inventory_by_user(db_session, user.user_id)
        assert len(items) == 1
        assert items[0].item_name == "Susu"

    def test_update_quantity(self, db_session):
        """Quantity harus bisa diperbarui."""
        _, item = self._create_user_and_item(db_session)
        updated = crud.update_inventory_quantity(db_session, item.item_id, 1)
        assert updated is not None
        assert updated.quantity == 1
        assert updated.status == StatusEnum.STORED

    def test_update_quantity_to_zero(self, db_session):
        """Quantity 0 harus mengubah status menjadi CONSUMED."""
        _, item = self._create_user_and_item(db_session)
        updated = crud.update_inventory_quantity(db_session, item.item_id, 0)
        assert updated is not None
        assert updated.quantity == 0
        assert updated.status == StatusEnum.CONSUMED

    def test_get_expiring_items(self, db_session):
        """Harus mendeteksi item yang mendekati kedaluwarsa."""
        self._create_user_and_item(db_session, "200", days_to_expire=2)
        self._create_user_and_item(db_session, "201", days_to_expire=30)
        expiring = crud.get_expiring_items(db_session, days_threshold=3)
        assert len(expiring) == 1

    def test_mark_consumed(self, db_session):
        """Item harus bisa ditandai sebagai CONSUMED."""
        _, item = self._create_user_and_item(db_session)
        consumed = crud.mark_inventory_consumed(db_session, item.item_id)
        assert consumed is not None
        assert consumed.status == StatusEnum.CONSUMED


# --- Test Scan Log ---


class TestScanLog:
    def test_create_scan_log(self, db_session):
        """Scan log harus tersimpan dengan benar."""
        user = crud.create_user(db_session, "300", "logger")
        item_data = {
            "user_id": user.user_id,
            "item_name": "Apel",
            "category": CategoryEnum.BUAH,
            "unit": "buah",
            "quantity": 5,
            "expiry_date": date.today() + timedelta(days=14),
            "expiry_source": ExpirySourceEnum.LLM_ESTIMATE,
        }
        item = crud.create_inventory_item(db_session, item_data)
        log = crud.create_scan_log(db_session, item.item_id, ActionEnum.CHECKIN, 5)
        assert log.action == ActionEnum.CHECKIN
        assert log.quantity_change == 5


# --- Test AI Parser (Mocked) ---


class TestAIParser:
    @patch("backend.intelligence.ai_parser.get_client")
    def test_parse_single_item(self, mock_get_client, tmp_path):
        """AI parser harus bisa menghasilkan list dari 1 item."""
        from backend.intelligence.ai_parser import parse_fridge_item_image

        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content='{"items": [{"item_name": "Susu", "category": "Kemasan", "quantity": 1, "unit": "kotak", "expiry_date": "2026-06-01", "freshness_condition": null, "estimated_days_to_expire": null}]}'
                )
            )
        ]
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        # Buat dummy image file
        img = tmp_path / "test.jpg"
        img.write_bytes(b"\xff\xd8\xff\xe0dummy_jpeg")

        result = parse_fridge_item_image(str(img))
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["item_name"] == "Susu"

    @patch("backend.intelligence.ai_parser.get_client")
    def test_parse_multi_item(self, mock_get_client, tmp_path):
        """AI parser harus bisa menghasilkan list dari multiple items."""
        from backend.intelligence.ai_parser import parse_fridge_item_image

        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content='{"items": [{"item_name": "Susu", "category": "Kemasan", "quantity": 1, "unit": "kotak", "expiry_date": null, "freshness_condition": null, "estimated_days_to_expire": 7}, {"item_name": "Apel", "category": "Buah", "quantity": 3, "unit": "buah", "expiry_date": null, "freshness_condition": "Segar", "estimated_days_to_expire": 14}]}'
                )
            )
        ]
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        img = tmp_path / "test2.jpg"
        img.write_bytes(b"\xff\xd8\xff\xe0dummy_jpeg")

        result = parse_fridge_item_image(str(img))
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[1]["item_name"] == "Apel"
