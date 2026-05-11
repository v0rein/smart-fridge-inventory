import enum
from sqlalchemy import Column, Integer, String, Date, DateTime, ForeignKey, Enum
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func
import datetime

Base = declarative_base()


class CategoryEnum(enum.Enum):
    SAYUR = "Sayur"
    BUAH = "Buah"
    DAGING = "Daging"
    KEMASAN = "Kemasan"
    LAINNYA = "Lainnya"


class ExpirySourceEnum(enum.Enum):
    OCR = "ocr"
    LLM_ESTIMATE = "llm_estimate"
    MANUAL = "manual"


class StatusEnum(enum.Enum):
    STORED = "Stored"
    CONSUMED = "Consumed"
    EXPIRED = "Expired"


class ActionEnum(enum.Enum):
    CHECKIN = "checkin"
    CHECKOUT = "checkout"
    PARTIAL_CHECKOUT = "partial_checkout"


class User(Base):
    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_chat_id = Column(
        String, nullable=False, unique=True
    )  # SKPL-NF04: Should be encrypted in production
    username = Column(String(50), nullable=True)

    # Relationships
    inventory_items = relationship(
        "Inventory", back_populates="user", cascade="all, delete-orphan"
    )


class Inventory(Base):
    __tablename__ = "inventory"

    item_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    item_name = Column(String(100), nullable=False)
    category = Column(Enum(CategoryEnum), nullable=False, default=CategoryEnum.LAINNYA)
    unit = Column(String(30), nullable=False, default="buah")
    quantity = Column(Integer, nullable=False, default=1)
    purchase_date = Column(Date, nullable=False, default=datetime.date.today)
    expiry_date = Column(Date, nullable=False)
    expiry_source = Column(Enum(ExpirySourceEnum), nullable=False)
    status = Column(Enum(StatusEnum), nullable=False, default=StatusEnum.STORED)

    # Relationships
    user = relationship("User", back_populates="inventory_items")
    logs = relationship("ScanLog", back_populates="item", cascade="all, delete-orphan")


class ScanLog(Base):
    __tablename__ = "scan_logs"

    log_id = Column(Integer, primary_key=True, autoincrement=True)
    item_id = Column(Integer, ForeignKey("inventory.item_id"), nullable=False)
    action = Column(Enum(ActionEnum), nullable=False)
    quantity_change = Column(Integer, nullable=False)
    timestamp = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    image_path = Column(String, nullable=True)

    # Relationships
    item = relationship("Inventory", back_populates="logs")
