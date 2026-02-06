# -*- coding: utf-8 -*-
# backend_api/database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session, declarative_base
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    _project_root = Path(__file__).resolve().parents[1]
    load_dotenv(_project_root / ".env")
except Exception:
    pass

DB_USER = os.getenv("DB_USER", "root")
DB_PASS = os.getenv("DB_PASS", "")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "3306")
DB_NAME = os.getenv("DB_NAME", "password_guardian")

def _legacy_mysql_url() -> str:
    pw_part = f":{DB_PASS}" if DB_PASS else ""
    port_part = f":{DB_PORT}" if DB_PORT else ""
    return f"mysql+mysqlconnector://{DB_USER}{pw_part}@{DB_HOST}{port_part}/{DB_NAME}"

DATABASE_URL = os.getenv("DATABASE_URL", _legacy_mysql_url())

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=1800,
    future=True,
)

SessionLocal = scoped_session(sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True))
Base = declarative_base()

def get_session():
    """Context-managed session for Flask handlers."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
