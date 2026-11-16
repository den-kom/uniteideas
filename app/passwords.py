"""Optional passwords, hashed with scrypt from the standard library (no extra dependency).

Stored as: scrypt$<n>$<r>$<p>$<salt hex>$<hash hex>. The parameters travel with the hash so they
can be raised later without breaking old passwords.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

N, R, P = 2**14, 8, 1
MIN_LENGTH = 10
MAX_LENGTH = 200
_DUMMY = ""


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=N, r=R, p=P, dklen=32)
    return f"scrypt${N}${R}${P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    """Always does the same amount of work, so timing does not reveal whether an account exists."""
    global _DUMMY
    if not _DUMMY:
        _DUMMY = hash_password("not-a-real-password")
    candidate = stored or _DUMMY
    try:
        _, n, r, p, salt, expected = candidate.split("$")
        digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), dklen=32)
        ok = hmac.compare_digest(digest, bytes.fromhex(expected))
    except (ValueError, TypeError):
        return False
    return ok and stored is not None


def problem_with(password: str) -> str | None:
    if len(password) < MIN_LENGTH:
        return f"Use at least {MIN_LENGTH} characters"
    if len(password) > MAX_LENGTH:
        return "That password is too long"
    if password.lower() in {"password123", "passwordpassword", "1234567890", "qwertyuiop"}:
        return "That password is too easy to guess"
    return None
