import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.database.models import Base
from dotenv import load_dotenv

load_dotenv()

# Gunakan SQLite untuk development awal agar bisa langsung jalan tanpa setup server DB
# Untuk production, ganti DATABASE_URL ke PostgreSQL di file .env
# Contoh: DATABASE_URL="postgresql://user:password@localhost/sfi_db"
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./sfi_database.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Membuat semua tabel di database jika belum ada"""
    Base.metadata.create_all(bind=engine)


def get_db():
    """Generator untuk mendapatkan session database"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
