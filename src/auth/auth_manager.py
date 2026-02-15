# -*- coding: utf-8 -*-
# auth_manager.py - Updated with proper password hashing

import os
import builtins
from pathlib import Path
import random
import string
import secrets
import smtplib
import ssl
import hashlib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from database.engine import SessionLocal
from database.models import (
    User,
    OTPCode,
    ActivityLog,
    TrustedDevice,
    RecoveryCode,
    Session,
    UserDevice,
)
from sqlalchemy import select, update


def _safe_print(*args, **kwargs):
    try:
        builtins.print(*args, **kwargs)
    except UnicodeEncodeError:
        safe_args = [str(a).encode("ascii", "replace").decode("ascii") for a in args]
        builtins.print(*safe_args, **kwargs)


print = _safe_print  # type: ignore


# ----------------- Password Hashing -----------------
def hash_password(password: str, salt: str = None) -> tuple[str, str]:
    """
    Hash password using PBKDF2-HMAC-SHA256
    Returns: (password_hash, salt)
    """
    if salt is None:
        salt = os.urandom(32).hex()
    
    pwd_hash = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000  # 100,000 iterations
    )
    
    return pwd_hash.hex(), salt


def verify_password(stored_hash: str, salt: str, provided_password: str) -> bool:
    """
    Verify a password against its hash
    Returns: True if password matches
    """
    pwd_hash, _ = hash_password(provided_password, salt)
    return pwd_hash == stored_hash


# ----------------- Auth Manager Class -----------------
class AuthManager:
    def __init__(self):
        self.email_cfg = self._load_email_cfg()
        # in-memory caches
        self.pending_2fa: dict[object, dict] = {}
        self.pending_reset: dict[str, dict] = {}
        self.pending_verify: dict[str, dict] = {}
        self._last_password = None
        self.mfa_enabled_emails: set[str] = set()
        self.recovery_codes: dict[int, list[str]] = {}

    # ---- normalize email key ----
    def _key(self, email_or_key) -> object:
        if isinstance(email_or_key, str):
            return email_or_key.strip().lower()
        return email_or_key

    def _send_mail(self, to_email: str, subject: str, body: str, html: bool = False) -> bool:
        try:
            if not self.email_cfg.get("sender_email") or not self.email_cfg.get("sender_password"):
                raise RuntimeError("SMTP credentials missing. Check SMTP_USER / SMTP_PASSWORD in .env.")
            if not to_email:
                raise RuntimeError("Recipient email is empty.")
            msg = MIMEMultipart('alternative')
            msg['From'] = f"{self.email_cfg['sender_name']} <{self.email_cfg['sender_email']}>"
            msg['To'] = to_email
            msg['Subject'] = subject
            if self.email_cfg.get("reply_to"):
                msg['Reply-To'] = self.email_cfg["reply_to"]
            msg.attach(MIMEText(body, 'html' if html else 'plain'))

            timeout = int(self.email_cfg.get("timeout", 20))
            if self.email_cfg.get("use_ssl"):
                with smtplib.SMTP_SSL(
                    self.email_cfg["smtp_server"],
                    self.email_cfg["smtp_port"],
                    timeout=timeout,
                    context=ssl.create_default_context(),
                ) as s:
                    s.login(self.email_cfg["sender_email"], self.email_cfg["sender_password"])
                    s.send_message(msg)
            else:
                with smtplib.SMTP(
                    self.email_cfg["smtp_server"],
                    self.email_cfg["smtp_port"],
                    timeout=timeout,
                ) as s:
                    s.ehlo()
                    if self.email_cfg.get("use_starttls"):
                        s.starttls(context=ssl.create_default_context())
                        s.ehlo()
                    s.login(self.email_cfg["sender_email"], self.email_cfg["sender_password"])
                    s.send_message(msg)
            
            print(f"✅ Email sent to {to_email}")
            return True
        except Exception as e:
            print(f"❌ Email error: {e}")
            return False

    def _load_email_cfg(self) -> dict:
        # Load environment variables from project .env if available
        try:
            from dotenv import load_dotenv
            project_root = Path(__file__).resolve().parents[2]
            load_dotenv(project_root / ".env")
        except Exception:
            pass

        def _get_bool(name: str, default: bool = False) -> bool:
            val = os.getenv(name)
            if val is None:
                return default
            return val.strip().lower() in {"1", "true", "yes", "y", "on"}

        def _first_env(*names: str, default: str = "") -> str:
            for name in names:
                value = os.getenv(name)
                if value is not None and str(value).strip() != "":
                    return str(value).strip().strip("\"' ")
            return default

        smtp_port = int(_first_env("SMTP_PORT", default="587"))
        use_ssl = _get_bool("SMTP_USE_SSL", smtp_port == 465)
        use_starttls = _get_bool("SMTP_USE_STARTTLS", (not use_ssl and smtp_port in (587, 25)))

        return {
            "smtp_server": _first_env("SMTP_SERVER", "SMTP_HOST", default="smtp.gmail.com"),
            "smtp_port": smtp_port,
            "sender_email": _first_env("SMTP_USER", "SMTP_FROM_EMAIL"),
            "sender_password": _first_env("SMTP_PASSWORD"),
            "sender_name": _first_env("SMTP_FROM_NAME", default="Password Guardian"),
            "reply_to": _first_env("SMTP_REPLY_TO"),
            "use_ssl": use_ssl,
            "use_starttls": use_starttls,
            "timeout": int(_first_env("SMTP_TIMEOUT", default="20")),
        }

    def _gen_code(self, n=6) -> str:
        return ''.join(random.choice(string.digits) for _ in range(n))

    def _device_fingerprint(self) -> str:
        """Create a stable fingerprint for this machine."""
        import platform
        try:
            user = os.getlogin()
        except Exception:
            user = os.getenv("USERNAME") or os.getenv("USER") or "user"
        raw = f"{platform.node()}|{platform.system()}|{platform.release()}|{user}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _device_label(self) -> str:
        import platform
        try:
            user = os.getlogin()
        except Exception:
            user = os.getenv("USERNAME") or os.getenv("USER") or "user"
        return f"{platform.node()} ({platform.system()} {platform.release()}) - {user}"

    def _record_device_session(self, user_id: int) -> None:
        from datetime import datetime, timedelta
        device_name = self._device_label()
        now = datetime.utcnow()
        try:
            with SessionLocal() as s:
                existing = s.execute(
                    select(UserDevice).where(
                        UserDevice.user_id == user_id,
                        UserDevice.device_name == device_name,
                    )
                ).scalar_one_or_none()
                if existing:
                    existing.last_used = now
                else:
                    s.add(UserDevice(
                        user_id=user_id,
                        device_name=device_name,
                        ip_address=None,
                        last_used=now,
                    ))

                token = secrets.token_urlsafe(32)
                s.add(Session(
                    user_id=user_id,
                    session_token=token,
                    created_at=now,
                    expires_at=now + timedelta(days=30),
                    device_info=device_name,
                ))
                s.commit()
        except Exception:
            # do not block login if audit/session tracking fails
            pass

    # ------------ DB ops ------------
    def _user_by_email(self, email: str) -> dict | None:
        k = self._key(email) # thawes f database ela user b email taeo if laqo treturni info taweo 
        with SessionLocal() as s:
            row = s.execute(select(User).where(User.email == k)).first()
            if not row:
                return None
            u: User = row[0]
            return {
                "id": u.id,
                "username": u.username,
                "email": u.email,
                "password_hash": u.password_hash,
                "salt": u.salt,
                "email_verified": u.email_verified,
                "mfa_enabled": bool(u.mfa_enabled),
                "totp_enabled": bool(u.totp_enabled),
                "totp_secret": u.totp_secret,
            }

    def _set_password(self, email: str, new_password: str) -> bool:
        pw_hash, salt = hash_password(new_password)
        k = self._key(email)
        
        with SessionLocal() as s:
            s.execute(
                update(User)
                .where(User.email == k)
                .values(password_hash=pw_hash, salt=salt)
            )
            s.commit()
            return True

    def _create_user(self, username: str, email: str, password: str) -> int | None:
        pw_hash, salt = hash_password(password)
        k = self._key(email)
        
        with SessionLocal() as s:
            u = User(
                username=username,
                email=k,
                password_hash=pw_hash,
                salt=salt,
                email_verified=False,
                created_at=datetime.utcnow(),
            )
            s.add(u)
            s.commit()
            s.refresh(u)
            print(f"✅ User created: {username} (ID: {u.id})")
            return u.id

    # ------------ Public API ------------
    def register_user(self, username: str, email: str, password: str):
        existing = self._user_by_email(email)
        if existing:
            return False, "❌ Cet e-mail est déjà utilisé.", {}
        
        try:
            user_id = self._create_user(username, email, password)
            if not user_id:
                return False, "❌ Impossible de créer le compte.", {}

            code = self._gen_code()
            k = self._key(email)
            self.pending_verify[k] = {
                "code": str(code),
                "expires": datetime.utcnow() + timedelta(minutes=15),
                "user_id": user_id,
            }
            
            sent = self._send_mail(
                email,
                "Vérification de votre compte – Password Guardian",
                f"Bonjour {username},\n\nVotre code: {code}\n\nExpire dans 15 min.\n\nPassword Guardian"
            )
            if not sent:
                return (
                    False,
                    "❌ Impossible d'envoyer l'email de vérification. Vérifiez SMTP_USER / SMTP_PASSWORD / SMTP_PORT / SMTP_USE_SSL.",
                    {"user_id": user_id, "email": k},
                )
            
            print(f"[DEV] Registration code for {k}: {code}")
            return True, "✅ Code de vérification envoyé à votre e-mail.", {"user_id": user_id, "email": k}
            
        except Exception as e:
            print(f"❌ Registration error: {e}")
            return False, f"❌ Erreur lors de la création du compte: {e}", {}

    def verify_registration_code(self, email: str, code: str) -> bool:
        k = self._key(email)
        entry = self.pending_verify.get(k)
        
        if not entry:
            print(f"❌ No pending verification for {k}")
            return False
        
        if datetime.utcnow() > entry["expires"]:
            print(f"❌ Verification code expired for {k}")
            self.pending_verify.pop(k, None)
            return False
        
        if str(entry["code"]) != str(code).strip():
            print(f"❌ Invalid registration code for {k}")
            return False
        
        with SessionLocal() as s:
            s.execute(update(User).where(User.email == k).values(email_verified=True))
            s.commit()
        
        print(f"✅ User verified: {k}")
        self.pending_verify.pop(k, None)
        return True

    def authenticate(self, email: str, password: str, send_2fa: bool = True) -> dict:
        """Authenticate user and enforce MFA (TOTP or email OTP)."""
        try:
            u = self._user_by_email(email)
            
            if not u:
                return {
                    "error": "❌ Aucun compte trouvé avec cet email.\n\nVeuillez créer un compte.", 
                    "2fa_sent": False
                }
            
            # Check email verification
            if not u.get("email_verified"):
                return {
                    "error": (
                        "❌ Email non vérifié.\n\n"
                        "Veuillez vérifier votre boîte mail et entrer le code de vérification.\n\n"
                        "Si vous n'avez pas reçu le code, créez un nouveau compte."
                    ),
                    "2fa_sent": False,
                    "email_not_verified": True,
                    "user": {
                        "id": u['id'],
                        "username": u['username'],
                        "email": u['email']
                    }
                }
            
            # Verify password using hashing
            if not verify_password(u["password_hash"], u["salt"], password):
                return {
                    "error": "❌ Mot de passe incorrect.\n\nVeuillez réessayer.", 
                    "2fa_sent": False
                }

            self._last_password = password
            totp_enabled = bool(u.get("totp_enabled") and u.get("totp_secret"))

            if totp_enabled:
                trusted = False
                try:
                    trusted = self.is_device_trusted(u["id"])
                except Exception:
                    trusted = False

                if trusted:
                    self._record_device_session(u["id"])
                else:
                    return {
                        "error": None,
                        "2fa_sent": False,
                        "mfa_required": True,
                        "mfa_method": "totp",
                        "user": {
                            "id": u["id"],
                            "username": u["username"],
                            "email": u["email"],
                            "salt": u["salt"],
                            "mfa_enabled": bool(u.get("mfa_enabled")),
                            "totp_enabled": True,
                        },
                    }

            sent = False
            if send_2fa:
                sent = self.send_2fa_code(email, u["id"], "login")
            # If 2FA is not used or could not be sent, record device/session now
            if not send_2fa or not sent:
                self._record_device_session(u["id"])
            return {
                "error": None,
                "2fa_sent": sent,
                "mfa_required": False,
                "user": {
                    "id": u["id"],
                    "username": u["username"],
                    "email": u["email"],
                    "salt": u["salt"],
                    "mfa_enabled": bool(u.get("mfa_enabled")),
                    "totp_enabled": bool(u.get("totp_enabled")),
                }
            }
            
        except Exception as e:
            print(f"❌ Authentication error: {e}")
            import traceback
            traceback.print_exc()
            return {"error": f"❌ Erreur: {e}", "2fa_sent": False}

    def verify_2fa_email(self, email: str, code: str) -> bool:
        k = self._key(email)
        entry = self.pending_2fa.get(k)
        
        if not entry:
            print(f"❌ No pending 2FA for {k}")
            return False
        
        if datetime.utcnow() > entry["expires"]:
            print(f"❌ 2FA code expired for {k}")
            self.pending_2fa.pop(k, None)
            return False
        
        ok = (str(entry["code"]) == str(code).strip())
        if ok:
            print(f"✅ 2FA verified for {k}")
            self.pending_2fa.pop(k, None)
            try:
                uid = entry.get("user_id") or (self._user_by_email(k) or {}).get("id")
                if uid:
                    self._record_device_session(uid)
            except Exception:
                pass
        else:
            print(f"❌ Invalid 2FA code for {k}")
        
        return ok

    def send_2fa_code(self, to_email: str, user_id: int | None = None, purpose: str = "sensitive_action") -> bool:
        u = self._user_by_email(to_email)
        if not u:
            print(f"❌ User not found: {to_email}")
            return False
        
        code = self._gen_code()
        expiry = datetime.utcnow() + timedelta(minutes=5)
        k = self._key(to_email)
        
        self.pending_2fa[k] = {
            "code": str(code), 
            "expires": expiry, 
            "purpose": purpose, 
            "user_id": u['id']
        }
        
        if user_id is not None:
            self.pending_2fa[user_id] = {
                "code": str(code), 
                "expires": expiry, 
                "purpose": purpose
            }
        
        print(f"[DEV] 2FA code for {k} ({purpose}): {code}")
        
        html = f"""
        <html><body>
        <h2>🔐 Vérification de sécurité</h2>
        <p>Code: <b style="font-size:24px;letter-spacing:6px;">{code}</b></p>
        <p>Ce code expire dans 5 minutes.</p>
        </body></html>
        """
        return self._send_mail(to_email, "🔐 Code de vérification - Password Guardian", html, html=True)

    def verify_2fa(self, user_id_or_email, code: str) -> bool:
        key = self._key(user_id_or_email) if isinstance(user_id_or_email, str) else user_id_or_email
        entry = self.pending_2fa.get(key)
        
        if not entry:
            print(f"❌ No 2FA code found for: {key}")
            return False
        
        if datetime.utcnow() > entry["expires"]:
            print(f"⏰ 2FA code expired for: {key}")
            self.pending_2fa.pop(key, None)
            return False
        
        if str(entry["code"]) == str(code).strip():
            print(f"✅ 2FA code verified for: {key}")
            self.pending_2fa.pop(key, None)
            return True
        
        print(f"❌ Invalid 2FA code for: {key}")
        return False

    def send_reset_code(self, email: str) -> bool:
        u = self._user_by_email(email)
        if not u:
            print(f"❌ User not found for reset: {email}")
            return False
        
        code = self._gen_code()
        k = self._key(email)
        self.pending_reset[k] = {
            "code": str(code), 
            "expires": datetime.utcnow() + timedelta(minutes=15)
        }
        
        ok = self._send_mail(
            email,
            "Réinitialisation du mot de passe – Password Guardian",
            f"Bonjour {u['username']},\n\nVotre code: {code}\n\nExpire dans 15 min.\n\nPassword Guardian"
        )
        
        if ok:
            print(f"[DEV] Reset code for {k}: {code}")
        
        return ok

    def verify_reset_code(self, email: str, code: str) -> bool:
        k = self._key(email)
        entry = self.pending_reset.get(k)
        
        if not entry:
            return False
        
        return (str(entry["code"]) == str(code).strip() 
                and datetime.utcnow() < entry["expires"])

    def update_password_with_code(self, email: str, code: str, new_password: str) -> bool:
        if not self.verify_reset_code(email, code):
            print(f"❌ Invalid reset code for {email}")
            return False
        
        ok = self._set_password(email, new_password)
        if ok:
            self.pending_reset.pop(self._key(email), None)
            print(f"✅ Password updated for {email}")
        
        return ok
    
    def resend_verification_code(self, email: str) -> bool:
        """Resend email verification code"""
        k = self._key(email)
        
        u = self._user_by_email(email)
        if not u:
            print(f"❌ User not found: {email}")
            return False
        
        if u.get('email_verified'):
            print(f"ℹ️ Email already verified: {email}")
            return False
        
        code = self._gen_code()
        self.pending_verify[k] = {
            "code": str(code),
            "expires": datetime.utcnow() + timedelta(minutes=15),
            "user_id": u['id'],
        }
        
        sent = self._send_mail(
            email,
            "Vérification de votre compte – Password Guardian",
            f"Bonjour {u['username']},\n\n"
            f"Votre nouveau code de vérification: {code}\n\n"
            f"Ce code expire dans 15 minutes.\n\n"
            f"Password Guardian"
        )
        if not sent:
            return False
        
        print(f"[DEV] New verification code for {k}: {code}")
        return True

    def change_unverified_email(self, current_email: str, new_email: str) -> tuple[bool, str, str | None]:
        """Change email for an unverified account, then resend verification code."""
        old_k = self._key(current_email)
        new_k = self._key(new_email)

        if not isinstance(new_k, str) or "@" not in new_k or "." not in new_k:
            return False, "❌ Nouvelle adresse email invalide.", None

        with SessionLocal() as s:
            user = s.execute(select(User).where(User.email == old_k)).scalar_one_or_none()
            if not user:
                return False, "❌ Compte introuvable.", None
            if bool(user.email_verified):
                return False, "❌ Cet email est déjà vérifié.", None

            exists = (
                s.execute(select(User).where(User.email == new_k).where(User.id != user.id))
                .scalar_one_or_none()
            )
            if exists:
                return False, "❌ Cet e-mail est déjà utilisé.", None

            user.email = new_k
            s.commit()

        pending_entry = self.pending_verify.pop(old_k, None)
        if pending_entry:
            self.pending_verify[new_k] = pending_entry

        sent = self.resend_verification_code(new_k)
        if not sent:
            with SessionLocal() as s:
                user = s.execute(select(User).where(User.email == new_k)).scalar_one_or_none()
                if user:
                    user.email = old_k
                    s.commit()
            if pending_entry:
                self.pending_verify.pop(new_k, None)
                self.pending_verify[old_k] = pending_entry
            return False, "❌ Changement effectué mais envoi impossible. Vérifiez la config SMTP.", None

        return True, "✅ Email mis à jour. Nouveau code envoyé.", new_k

    # ---------- Audit logs ----------
    def list_audit_logs(self, user_id: int, filter_key: str = "all") -> list[dict]:
        with SessionLocal() as s:
            q = select(ActivityLog).where(ActivityLog.user_id == int(user_id))
            if filter_key and filter_key != "all":
                q = q.where(ActivityLog.action.like(f"{filter_key}:%"))
            rows = s.execute(q.order_by(ActivityLog.created_at.desc())).scalars().all()
            return [
                {
                    "id": r.id,
                    "action": r.action,
                    "details": r.details,
                    "ip_address": r.ip_address,
                    "created_at": r.created_at,
                }
                for r in rows
            ]

    # ---------- MFA helpers (email-based + TOTP + recovery codes + device trust) ----------
    def set_mfa_enabled(self, email: str, enabled: bool) -> None:
        k = self._key(email)
        if enabled:
            self.mfa_enabled_emails.add(k)
        else:
            self.mfa_enabled_emails.discard(k)

    def is_mfa_enabled(self, email: str) -> bool:
        u = self._user_by_email(email)
        if u:
            return bool(u.get("mfa_enabled") or u.get("totp_enabled"))
        return self._key(email) in self.mfa_enabled_emails

    def is_totp_enabled(self, email: str) -> bool:
        u = self._user_by_email(email)
        return bool(u and u.get("totp_enabled"))

    def enable_totp(self, email: str) -> dict:
        """Enable TOTP for user, return secret + provisioning URI."""
        try:
            import pyotp
        except Exception as e:
            return {"error": f"pyotp is required for TOTP: {e}"}
        u = self._user_by_email(email)
        if not u:
            return {"error": "User not found"}
        secret = pyotp.random_base32()
        with SessionLocal() as s:
            s.execute(
                update(User)
                .where(User.email == self._key(email))
                .values(totp_secret=secret, totp_enabled=True, mfa_enabled=True)
            )
            s.commit()
        uri = pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name="Password Guardian")
        return {"secret": secret, "uri": uri}

    def disable_totp(self, email: str) -> bool:
        try:
            with SessionLocal() as s:
                s.execute(
                    update(User)
                    .where(User.email == self._key(email))
                    .values(totp_secret=None, totp_enabled=False)
                )
                s.commit()
            return True
        except Exception:
            return False

    def verify_totp(self, email: str, code: str) -> bool:
        try:
            import pyotp
        except Exception:
            return False
        u = self._user_by_email(email)
        if not u or not u.get("totp_secret"):
            return False
        return pyotp.TOTP(u["totp_secret"]).verify(str(code).strip(), valid_window=1)

    def _hash_recovery(self, code: str, salt: str) -> str:
        return hashlib.sha256((salt + str(code)).encode("utf-8")).hexdigest()

    def generate_recovery_codes(self, user_id: int, count: int = 8) -> list[str]:
        """Generate and store hashed recovery codes, return plaintext once."""
        u = None
        with SessionLocal() as s:
            u = s.get(User, int(user_id))
            if not u:
                return []
            # delete old codes
            s.query(RecoveryCode).filter(RecoveryCode.user_id == int(user_id)).delete()
            codes: list[str] = []
            for _ in range(max(1, count)):
                c = self._gen_code(8)
                codes.append(c)
                s.add(RecoveryCode(user_id=int(user_id), code_hash=self._hash_recovery(c, u.salt)))
            s.commit()
            return codes

    def list_recovery_codes(self, user_id: int) -> list[str]:
        # For security, return empty (only shown at generation time)
        return []

    def verify_recovery_code(self, user_id: int, code: str) -> bool:
        with SessionLocal() as s:
            u = s.get(User, int(user_id))
            if not u:
                return False
            h = self._hash_recovery(code, u.salt)
            rc = (
                s.query(RecoveryCode)
                .filter(RecoveryCode.user_id == int(user_id))
                .filter(RecoveryCode.code_hash == h)
                .filter(RecoveryCode.used_at.is_(None))
                .first()
            )
            if not rc:
                return False
            rc.used_at = datetime.utcnow()
            s.commit()
            return True

    def trust_device(self, user_id: int, device_name: str | None = None, days: int = 30) -> bool:
        fp = self._device_fingerprint()
        name = device_name or fp[:12]
        now = datetime.utcnow()
        until = now + timedelta(days=days)
        with SessionLocal() as s:
            td = (
                s.query(TrustedDevice)
                .filter(TrustedDevice.user_id == int(user_id))
                .filter(TrustedDevice.device_fingerprint == fp)
                .first()
            )
            if td:
                td.trusted_until = until
                td.last_used = now
                td.device_name = name
            else:
                s.add(
                    TrustedDevice(
                        user_id=int(user_id),
                        device_fingerprint=fp,
                        device_name=name,
                        trusted_until=until,
                        created_at=now,
                        last_used=now,
                    )
                )
            s.commit()
        return True

    def is_device_trusted(self, user_id: int) -> bool:
        fp = self._device_fingerprint()
        now = datetime.utcnow()
        with SessionLocal() as s:
            td = (
                s.query(TrustedDevice)
                .filter(TrustedDevice.user_id == int(user_id))
                .filter(TrustedDevice.device_fingerprint == fp)
                .filter(TrustedDevice.trusted_until > now)
                .first()
            )
            if td:
                td.last_used = now
                s.commit()
                return True
        return False
