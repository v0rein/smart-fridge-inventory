from sqlalchemy.orm import Session
from datetime import date
from typing import List, Optional

from backend.database.models import User, Inventory, ScanLog, ActionEnum, StatusEnum
from backend.database.encryption import encrypt, decrypt

# --- USER CRUD ---


def get_user_by_chat_id(db: Session, telegram_chat_id: str) -> Optional[User]:
    """Mencari user berdasarkan chat_id. Chat_id disimpan terenkripsi (SKPL-NF04)."""
    users = db.query(User).all()
    for user in users:
        try:
            if decrypt(str(user.telegram_chat_id)) == telegram_chat_id:
                return user
        except Exception:
            # Fallback: cek tanpa dekripsi (data lama yang belum dienkripsi)
            if str(user.telegram_chat_id) == telegram_chat_id:
                return user
    return None


def create_user(
    db: Session, telegram_chat_id: str, username: Optional[str] = None
) -> User:
    """Membuat user baru dengan chat_id terenkripsi (SKPL-NF04)."""
    encrypted_chat_id = encrypt(telegram_chat_id)
    db_user = User(telegram_chat_id=encrypted_chat_id, username=username)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def get_all_users(db: Session) -> List[User]:
    """Mendapatkan semua user yang terdaftar (untuk notifikasi harian)."""
    return db.query(User).all()


def get_decrypted_chat_id(user: User) -> str:
    """Mendekripsi chat_id user untuk pengiriman pesan."""
    try:
        return decrypt(str(user.telegram_chat_id))
    except Exception:
        return str(user.telegram_chat_id)


# --- INVENTORY CRUD ---


def create_inventory_item(db: Session, item_data: dict) -> Inventory:
    db_item = Inventory(**item_data)
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item


def get_active_inventory_by_user(db: Session, user_id: int) -> List[Inventory]:
    return (
        db.query(Inventory)
        .filter(Inventory.user_id == user_id, Inventory.status == StatusEnum.STORED)
        .all()
    )


def get_inventory_item(db: Session, item_id: int) -> Optional[Inventory]:
    return db.query(Inventory).filter(Inventory.item_id == item_id).first()


def update_inventory_quantity(
    db: Session, item_id: int, new_quantity: int
) -> Optional[Inventory]:
    db_item = get_inventory_item(db, item_id)
    if db_item:
        if new_quantity <= 0:
            db_item.status = StatusEnum.CONSUMED  # type: ignore
            db_item.quantity = 0  # type: ignore
        else:
            db_item.quantity = new_quantity  # type: ignore
        db.commit()
        db.refresh(db_item)
    return db_item


def mark_inventory_consumed(db: Session, item_id: int) -> Optional[Inventory]:
    db_item = get_inventory_item(db, item_id)
    if db_item:
        db_item.status = StatusEnum.CONSUMED  # type: ignore
        db.commit()
        db.refresh(db_item)
    return db_item


def get_expiring_items(db: Session, days_threshold: int = 3) -> List[Inventory]:
    """Mendapatkan semua item yang mendekati tanggal kedaluwarsa"""
    from datetime import timedelta

    target_date = date.today() + timedelta(days=days_threshold)
    return (
        db.query(Inventory)
        .filter(
            Inventory.status == StatusEnum.STORED, Inventory.expiry_date <= target_date
        )
        .all()
    )


# --- SCAN LOG CRUD ---


def create_scan_log(
    db: Session,
    item_id: int,
    action: ActionEnum,
    quantity_change: int,
    image_path: Optional[str] = None,
) -> ScanLog:
    db_log = ScanLog(
        item_id=item_id,
        action=action,
        quantity_change=quantity_change,
        image_path=image_path,
    )
    db.add(db_log)
    db.commit()
    db.refresh(db_log)
    return db_log
