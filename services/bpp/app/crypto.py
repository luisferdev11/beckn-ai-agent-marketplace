"""AES-256-GCM decryption compatible with the Node.js crypto.ts encrypt()."""

from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

IV_LENGTH = 12
TAG_LENGTH = 16


def _get_key() -> bytes:
    hex_key = os.getenv("CREDENTIALS_ENCRYPTION_KEY", "")
    if len(hex_key) != 64:
        raise RuntimeError("CREDENTIALS_ENCRYPTION_KEY must be 32 bytes (64 hex chars)")
    return bytes.fromhex(hex_key)


def decrypt(encoded: str) -> str:
    """Decrypt a base64-encoded payload produced by crypto.ts encrypt()."""
    raw = base64.b64decode(encoded)
    iv = raw[:IV_LENGTH]
    # AESGCM expects ciphertext+tag concatenated (which is how we packed it)
    ciphertext_and_tag = raw[IV_LENGTH:]
    aesgcm = AESGCM(_get_key())
    plaintext = aesgcm.decrypt(iv, ciphertext_and_tag, None)
    return plaintext.decode("utf-8")
