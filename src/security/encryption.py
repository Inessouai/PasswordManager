# -*- coding: utf-8 -*-
# src/security/encryption.py
import base64
import json
import hashlib
from cryptography.fernet import Fernet
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes


# ============================================================
# MASTER PASSWORD
# ============================================================
MASTER_PASSWORD = "YourSecretMasterPassword2024!".encode("utf-8")
SALT = b"salt_password_guardian_2024"


# ============================================================
# FERNET KEY (used by backend)
# ============================================================
def get_fernet_key():
    """
    Generates the same AES-256 Fernet key the backend uses.
    """
    kdf = hashlib.pbkdf2_hmac("sha256", MASTER_PASSWORD, SALT, 100000)
    return base64.urlsafe_b64encode(kdf[:32])


FERNET = Fernet(get_fernet_key())


# ============================================================
# AES-GCM (old GUI format)
# ============================================================
def derive_key():
    """
    Derives a 32-byte AES-GCM key from MASTER_PASSWORD.
    """
    return hashlib.pbkdf2_hmac("sha256", MASTER_PASSWORD, b"legacy_aes_gcm_salt", 200000)


AES_GCM_KEY = derive_key()


def encrypt_aes_gcm(plaintext: str) -> str:
    """
    Encrypts using legacy AES-GCM format used by old GUI.
    Output format: gcm1:<base64>
    """
    plaintext_bytes = plaintext.encode("utf-8")
    iv = get_random_bytes(12)

    cipher = AES.new(AES_GCM_KEY, AES.MODE_GCM, nonce=iv)
    ciphertext, tag = cipher.encrypt_and_digest(plaintext_bytes)

    payload = iv + tag + ciphertext
    token = "gcm1:" + base64.b64encode(payload).decode("utf-8")

    return token


def decrypt_aes_gcm(token: str) -> str:
    """
    Decrypts AES-GCM tokens of format gcm1:<base64>
    """
    try:
        b64 = token.split("gcm1:")[1]
        decoded = base64.b64decode(b64)

        iv = decoded[:12]
        tag = decoded[12:28]
        ciphertext = decoded[28:]

        cipher = AES.new(AES_GCM_KEY, AES.MODE_GCM, nonce=iv)
        plaintext = cipher.decrypt_and_verify(ciphertext, tag)

        return plaintext.decode("utf-8")

    except Exception as e:
        raise ValueError(f"AES-GCM decryption failed: {e}")


# ============================================================
# AUTO-DETECT DECRYPT ENGINE
# ============================================================
def decrypt_any(token: str) -> str:
    """
    AUTO-DETECT encryption format and decrypt accordingly.
    """
    if not token:
        raise ValueError("Empty token cannot be decrypted")

    # Convert bytes → str
    if isinstance(token, bytes):
        token = token.decode("utf-8", errors="ignore")

    # -----------------------------
    # Detect Fernet (backend)
    # Fernet tokens always start with: gAAAAA...
    # -----------------------------
    if token.startswith("gAAAA"):
        try:
            return FERNET.decrypt(token.encode("utf-8")).decode("utf-8")
        except Exception as e:
            raise ValueError(f"Fernet decryption failed: {e}")

    # -----------------------------
    #  Detect AES-GCM (old GUI)
    # -----------------------------
    if token.startswith("gcm1:"):
        return decrypt_aes_gcm(token)

    # -----------------------------
    # Unknown / corrupted
    # -----------------------------
    raise ValueError("Unknown encryption format.")


# ============================================================
# UNIVERSAL ENCRYPT (GUI USES FERNET BY DEFAULT)
# ============================================================
def encrypt_for_storage(plaintext: str) -> str:
    """
    Encrypt using FERNET (same as backend).
    """
    try:
        return FERNET.encrypt(plaintext.encode("utf-8")).decode("utf-8")
    except Exception as e:
        raise ValueError(f"Fernet encryption failed: {e}")


# ============================================================
# VAULT EXPORT (AES-GCM + Argon2id)
# ============================================================
def _argon2_key(
    passphrase: str,
    salt: bytes,
    time_cost: int = 3,
    memory_cost: int = 65536,
    parallelism: int = 2,
    hash_len: int = 32,
) -> bytes:
    try:
        from argon2.low_level import hash_secret_raw, Type
    except Exception as e:
        raise RuntimeError("argon2-cffi is required for vault encryption") from e

    return hash_secret_raw(
        secret=passphrase.encode("utf-8"),
        salt=salt,
        time_cost=time_cost,
        memory_cost=memory_cost,
        parallelism=parallelism,
        hash_len=hash_len,
        type=Type.ID,
    )


def encrypt_vault_payload(vault: dict, passphrase: str) -> dict:
    if not passphrase:
        raise ValueError("Passphrase required")

    salt = get_random_bytes(16)
    nonce = get_random_bytes(12)
    kdf_params = {
        "name": "argon2id",
        "time_cost": 3,
        "memory_cost": 65536,
        "parallelism": 2,
        "hash_len": 32,
    }
    # _argon2_key does not accept "name"
    _kdf = {k: v for k, v in kdf_params.items() if k != "name"}
    key = _argon2_key(passphrase, salt, **_kdf)

    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
    plaintext = json.dumps(vault, ensure_ascii=True).encode("utf-8")
    ciphertext, tag = cipher.encrypt_and_digest(plaintext)

    return {
        "format": "pgvault",
        "version": 1,
        "kdf": kdf_params,
        "salt": base64.b64encode(salt).decode("utf-8"),
        "nonce": base64.b64encode(nonce).decode("utf-8"),
        "tag": base64.b64encode(tag).decode("utf-8"),
        "ciphertext": base64.b64encode(ciphertext).decode("utf-8"),
    }


def decrypt_vault_payload(blob: dict, passphrase: str) -> dict:
    if not passphrase:
        raise ValueError("Passphrase required")
    if not isinstance(blob, dict) or blob.get("format") != "pgvault":
        raise ValueError("Invalid vault format")

    kdf = blob.get("kdf") or {}
    salt = base64.b64decode(blob.get("salt", ""))
    nonce = base64.b64decode(blob.get("nonce", ""))
    tag = base64.b64decode(blob.get("tag", ""))
    ciphertext = base64.b64decode(blob.get("ciphertext", ""))

    key = _argon2_key(
        passphrase,
        salt,
        time_cost=int(kdf.get("time_cost", 3)),
        memory_cost=int(kdf.get("memory_cost", 65536)),
        parallelism=int(kdf.get("parallelism", 2)),
        hash_len=int(kdf.get("hash_len", 32)),
    )
    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
    plaintext = cipher.decrypt_and_verify(ciphertext, tag)
    return json.loads(plaintext.decode("utf-8"))
