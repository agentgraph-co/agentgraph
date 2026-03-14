"""Token encryption helpers using Fernet symmetric encryption."""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet

from src.config import settings


def _get_fernet() -> Fernet:
    """Derive a Fernet key from the JWT secret."""
    # Fernet requires a 32-byte url-safe base64 key.
    # Derive deterministically from jwt_secret.
    key_bytes = hashlib.sha256(settings.jwt_secret.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key_bytes))


def encrypt_token(plaintext: str) -> str:
    """Encrypt a token string. Returns base64-encoded ciphertext."""
    f = _get_fernet()
    return f.encrypt(plaintext.encode()).decode()


def decrypt_token(ciphertext: str) -> str:
    """Decrypt a token string. Returns plaintext."""
    f = _get_fernet()
    return f.decrypt(ciphertext.encode()).decode()
