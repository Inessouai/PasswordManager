# -*- coding: utf-8 -*-
"""database/engine.py

Pro/uni-friendly DB configuration:
- Uses DATABASE_URL if provided (MySQL/Postgres/SQLite).
- Defaults to local SQLite file (runs out-of-the-box, no MySQL required).
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    # Load environment variables from project .env if present
    from dotenv import load_dotenv
    _project_root = Path(__file__).resolve().parents[1]
    load_dotenv(_project_root / ".env")
except Exception:
    # If python-dotenv isn't available or .env missing, keep defaults
    pass
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

def _default_sqlite_url() -> str:
    # store DB file next to main.py (project root)
    return "sqlite:///password_guardian.db"

def _legacy_mysql_url() -> str | None:
    host = os.getenv("DB_HOST")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASS")
    name = os.getenv("DB_NAME")
    port = os.getenv("DB_PORT", "3306")
    if host and user and name:
        pw_part = f":{password}" if password else ""
        return f"mysql+mysqlconnector://{user}{pw_part}@{host}:{port}/{name}"
    return None

DATABASE_URL = os.getenv("DATABASE_URL") or _legacy_mysql_url() or _default_sqlite_url()

connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    # Needed for SQLite with threads (GUI + backend)
    connect_args = {"check_same_thread": False}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    # Import here to avoid circular imports on module load
    from database.models import Base
    Base.metadata.create_all(bind=engine)

    # Lightweight migrations for SQLite (add new columns if missing)
    if DATABASE_URL.startswith("sqlite"):
        from sqlalchemy import text

        with engine.begin() as conn:
            def _has_column(table: str, column: str) -> bool:
                rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
                return any(r[1] == column for r in rows)

            if not _has_column("users", "mfa_enabled"):
                conn.execute(text("ALTER TABLE users ADD COLUMN mfa_enabled BOOLEAN DEFAULT 0"))
            if not _has_column("users", "totp_enabled"):
                conn.execute(text("ALTER TABLE users ADD COLUMN totp_enabled BOOLEAN DEFAULT 0"))
            if not _has_column("users", "totp_secret"):
                conn.execute(text("ALTER TABLE users ADD COLUMN totp_secret VARCHAR(64)"))
