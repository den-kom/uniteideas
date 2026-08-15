"""Encryption for sealed idea detail.

Trade-off: the key is derived from SECRET_KEY, so the server can decrypt. This
protects against casual disclosure and database leaks, not against the operator.
True zero-knowledge sealing needs client-held keys, which breaks collaboration
and agent-assisted builds — see docs/PROOF_AND_SEALING.md.
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


def _fernet() -> Fernet:
    secret = get_settings().secret_key.encode()
    key = base64.urlsafe_b64encode(hashlib.sha256(secret).digest())
    return Fernet(key)


def seal(plaintext: str) -> str:
    if not plaintext.strip():
        return ""
    return _fernet().encrypt(plaintext.encode()).decode()


def unseal(blob: str) -> str:
    if not blob:
        return ""
    try:
        return _fernet().decrypt(blob.encode()).decode()
    except InvalidToken:
        return "[sealed detail could not be decrypted — SECRET_KEY changed?]"
