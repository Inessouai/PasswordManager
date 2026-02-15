# -*- coding: utf-8 -*-
# backend_api/models.py
from sqlalchemy import (
    Column, Integer, String, Text, Enum, Boolean,
    DateTime, ForeignKey, TIMESTAMP
)
from sqlalchemy.orm import relationship, Mapped, mapped_column
from datetime import datetime
from .database import Base

CategoryEnum = Enum('personal','work','finance','study','game','trash', name="category_enum", native_enum=False)
StrengthEnum = Enum('weak','medium','strong', name="strength_enum", native_enum=False)

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), nullable=False)
    email: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    salt: Mapped[str] = mapped_column(String(255), nullable=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=datetime.utcnow)
    last_login: Mapped[datetime | None] = mapped_column(TIMESTAMP, nullable=True)

    passwords = relationship("Password", back_populates="user", cascade="all, delete-orphan")

class Password(Base):
    __tablename__ = "passwords"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    site_name: Mapped[str] = mapped_column(String(100), nullable=False)
    site_icon: Mapped[str] = mapped_column(String(10), default="🔒")
    username: Mapped[str] = mapped_column(String(255), nullable=False)
    encrypted_password: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(CategoryEnum, default="personal")
    strength: Mapped[str] = mapped_column(StrengthEnum, default="medium")
    favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    trashed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, nullable=True)
    last_updated: Mapped[datetime] = mapped_column(TIMESTAMP, default=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=datetime.utcnow)

    user = relationship("User", back_populates="passwords")
    history = relationship("PasswordHistory", back_populates="password", cascade="all, delete-orphan")

class PasswordHistory(Base):
    __tablename__ = "password_history"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    password_id: Mapped[int] = mapped_column(ForeignKey("passwords.id", ondelete="CASCADE"), nullable=False)
    old_encrypted_password: Mapped[str] = mapped_column(Text, nullable=False)
    changed_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=datetime.utcnow)

    password = relationship("Password", back_populates="history")


class OTPCode(Base):
    __tablename__ = "otp_codes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(6))
    purpose: Mapped[str] = mapped_column(String(50), default="login")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)

class Session(Base):
    __tablename__ = "sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    session_token: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False)
    device_info: Mapped[str | None] = mapped_column(String(255))

class UserDevice(Base):
    __tablename__ = "user_devices"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    device_name: Mapped[str] = mapped_column(String(255))
    ip_address: Mapped[str | None] = mapped_column(String(45))
    last_used: Mapped[datetime] = mapped_column(TIMESTAMP, default=datetime.utcnow)

class ActivityLog(Base):
    __tablename__ = "activity_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    action: Mapped[str] = mapped_column(String(100))
    details: Mapped[str | None] = mapped_column(Text)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=datetime.utcnow)
