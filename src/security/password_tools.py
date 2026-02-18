# -*- coding: utf-8 -*-
"""Password tooling (generator + strength analysis).

Uni-project "pro" additions:
- Password generator using `secrets`.
- Strength scoring + entropy estimate (easy to justify in a report).
"""

from __future__ import annotations

import math
import secrets
import string
import hashlib
import requests
from dataclasses import dataclass


@dataclass(frozen=True)
class GeneratorOptions:
    length: int = 16
    use_upper: bool = True
    use_lower: bool = True
    use_digits: bool = True
    use_symbols: bool = True


SYMBOLS = "!@#$%^&*()-_=+[]{};:,.<>/"


def generate_password(opts: GeneratorOptions | None = None) -> str:
    if opts is None:
        opts = GeneratorOptions()

    pools: list[str] = []
    if opts.use_upper:
        pools.append(string.ascii_uppercase)
    if opts.use_lower:
        pools.append(string.ascii_lowercase)
    if opts.use_digits:
        pools.append(string.digits)
    if opts.use_symbols:
        pools.append(SYMBOLS)

    if not pools:
        raise ValueError("Select at least one character group")

    alphabet = "".join(pools)

    # Ensure at least one from each selected pool
    password_chars = [secrets.choice(pool) for pool in pools]
    password_chars += [secrets.choice(alphabet) for _ in range(max(0, opts.length - len(password_chars)))]
    secrets.SystemRandom().shuffle(password_chars)
    return "".join(password_chars)


def estimate_entropy_bits(password: str) -> float:
    """Rough entropy estimate based on character set size and length."""
    if not password:
        return 0.0

    charset = 0
    if any(c.islower() for c in password):
        charset += 26
    if any(c.isupper() for c in password):
        charset += 26
    if any(c.isdigit() for c in password):
        charset += 10
    if any(c in SYMBOLS for c in password):
        charset += len(SYMBOLS)

    if charset <= 1:
        return 0.0

    return len(password) * math.log2(charset)


def strength_label(password: str) -> str:
    """Simple, explainable scoring → weak/medium/strong."""
    score = 0
    if len(password) >= 8:
        score += 1
    if len(password) >= 12:
        score += 1
    if len(password) >= 16:
        score += 1
    if any(c.islower() for c in password):
        score += 1
    if any(c.isupper() for c in password):
        score += 1
    if any(c.isdigit() for c in password):
        score += 1
    if any(c in SYMBOLS for c in password):
        score += 1

    # Penalty for repetition
    if len(set(password)) <= max(3, len(password) // 4):
        score -= 1

    if score <= 3:
        return "weak"
    if score <= 5:
        return "medium"
    return "strong"


def check_pwned_password(password: str, timeout: int = 5) -> tuple[bool, int]:
    """Check a password with HIBP using k-anonymity.

    Privacy model:
    - Compute SHA1 locally.
    - Send only first 5 hex chars (prefix) to HIBP `/range/{prefix}`.
    - Compare returned suffixes locally; full hash is never transmitted.

    Returns:
    - (is_compromised, breach_count)
    """
    if not password:
        return False, 0

    # Keep the password exactly as entered (spaces are significant).
    sha1_hash = hashlib.sha1(password.encode("utf-8")).hexdigest().upper()
    prefix, suffix = sha1_hash[:5], sha1_hash[5:]
    url = f"https://api.pwnedpasswords.com/range/{prefix}"
    headers = {
        "User-Agent": "PasswordGuardian/1.0",
        # Ask HIBP to pad results to reduce traffic-analysis leakage.
        "Add-Padding": "true",
    }
    # Weak/common passwords often map to very large range responses.
    # Use a longer read timeout so those lookups don't fail early.
    req_timeout = (timeout, max(15, timeout * 4))

    try:
        resp = requests.get(url, timeout=req_timeout, headers=headers)
    except requests.RequestException:
        return False, 0

    if resp.status_code != 200:
        return False, 0

    for line in resp.text.splitlines():
        if ":" not in line:
            continue
        hash_suffix, count = line.split(":", 1)
        if hash_suffix.strip().upper() == suffix:
            try:
                return True, int(count.strip())
            except ValueError:
                return True, 0

    return False, 0
