"""Symmetric encryption for secrets stored at rest (e.g. webhook signing keys).

Uses Fernet (AES-128-CBC with HMAC-SHA256) from the cryptography package,
which is already installed as a transitive dependency of PyJWT[crypto].

When WEBHOOK_ENCRYPTION_KEY is not set, falls back to plaintext storage
with a startup warning.  Production deployments MUST set the key.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_fernet = None


def _get_fernet():
    global _fernet
    if _fernet is not None:
        return _fernet

    from src.config import settings

    if not settings.webhook_encryption_key:
        if not settings.debug:
            raise RuntimeError(
                "WEBHOOK_ENCRYPTION_KEY must be set in production. "
                "Generate with: python3 -c "
                "'from cryptography.fernet import Fernet; "
                "print(Fernet.generate_key().decode())'"
            )
        logger.warning(
            "WEBHOOK_ENCRYPTION_KEY not set — webhook signing keys stored in plaintext. "
            "Set this variable in production."
        )
        return None

    from cryptography.fernet import Fernet

    _fernet = Fernet(settings.webhook_encryption_key.encode())
    return _fernet


def encrypt_secret(plaintext: str) -> str:
    """Encrypt a secret for at-rest storage. Returns prefixed ciphertext."""
    f = _get_fernet()
    if f is None:
        return plaintext
    return "enc:" + f.encrypt(plaintext.encode()).decode()


def decrypt_secret(stored: str) -> str:
    """Decrypt a stored secret. Handles both encrypted and legacy plaintext."""
    if not stored.startswith("enc:"):
        return stored  # Legacy plaintext — not yet migrated
    f = _get_fernet()
    if f is None:
        raise ValueError("Cannot decrypt: WEBHOOK_ENCRYPTION_KEY not configured")
    return f.decrypt(stored[4:].encode()).decode()
