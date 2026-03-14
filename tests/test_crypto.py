"""Tests for token encryption helpers."""
from __future__ import annotations

import pytest

from src.crypto import decrypt_token, encrypt_token


def test_encrypt_decrypt_roundtrip():
    plaintext = "***REMOVED***"
    ciphertext = encrypt_token(plaintext)
    assert ciphertext != plaintext
    assert decrypt_token(ciphertext) == plaintext


def test_different_plaintexts_produce_different_ciphertexts():
    c1 = encrypt_token("token_a")
    c2 = encrypt_token("token_b")
    assert c1 != c2
