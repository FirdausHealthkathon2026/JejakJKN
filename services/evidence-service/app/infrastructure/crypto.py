"""Encrypt optional patient notes at rest."""

import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def encrypt_note(value: str, key_hex: str, context: str) -> bytes:
    nonce = os.urandom(12)
    return nonce + AESGCM(bytes.fromhex(key_hex)).encrypt(
        nonce, value.encode(), context.encode()
    )
