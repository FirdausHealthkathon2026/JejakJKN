"""Participant blind indexes, field encryption, and Ed25519 QR signing."""

import hashlib
import hmac
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import jwt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from jejakjkn_canonical.problems import Problem


def normalize_participant_number(value: str) -> str:
    return value.strip().upper()


def blind_index(value: str, key_hex: str) -> str:
    return hmac.new(
        bytes.fromhex(key_hex),
        normalize_participant_number(value).encode(),
        hashlib.sha256,
    ).hexdigest()


def encrypt_field(value: str, key_hex: str, aad: str) -> bytes:
    nonce = os.urandom(12)
    ciphertext = AESGCM(bytes.fromhex(key_hex)).encrypt(
        nonce, value.encode(), aad.encode()
    )
    return nonce + ciphertext


def decrypt_field(value: bytes, key_hex: str, aad: str) -> str:
    return (
        AESGCM(bytes.fromhex(key_hex))
        .decrypt(value[:12], value[12:], aad.encode())
        .decode()
    )


class QrSigner:
    issuer = "jejakjkn-encounter-service"
    audience = "jejakjkn-qr-redemption"

    def __init__(
        self, private_key_path: Path, public_key_path: Path, kid: str, ttl_seconds: int
    ) -> None:
        self.private_key = private_key_path.read_bytes()
        self.public_key = public_key_path.read_bytes()
        self.kid = kid
        self.ttl_seconds = ttl_seconds

    def issue(
        self,
        *,
        nonce: str,
        patient_id: UUID,
        purpose: str,
        encounter_id: UUID | None,
        facility_hint: str | None,
    ) -> tuple[str, datetime]:
        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=self.ttl_seconds)
        payload = {
            "iss": self.issuer,
            "aud": self.audience,
            "jti": nonce,
            "sub": str(patient_id),
            "pur": purpose,
            "enc": str(encounter_id) if encounter_id else None,
            "fch": facility_hint,
            "iat": now,
            "exp": expires_at,
        }
        return jwt.encode(
            payload, self.private_key, algorithm="EdDSA", headers={"kid": self.kid}
        ), expires_at

    def verify(self, token: str, expected_purpose: str) -> dict[str, Any]:
        try:
            claims = jwt.decode(
                token,
                self.public_key,
                algorithms=["EdDSA"],
                audience=self.audience,
                issuer=self.issuer,
                options={"require": ["exp", "iat", "jti", "sub", "pur"]},
            )
        except jwt.ExpiredSignatureError as exc:
            raise Problem(
                410,
                "QR_TOKEN_EXPIRED",
                "QR token expired",
                "Request a new QR token and scan it again.",
            ) from exc
        except jwt.PyJWTError as exc:
            raise Problem(
                401,
                "INVALID_QR_SIGNATURE",
                "Invalid QR token",
                "The QR token signature or claims are invalid.",
            ) from exc
        if claims["pur"] != expected_purpose:
            raise Problem(
                422,
                "WRONG_QR_PURPOSE",
                "Wrong QR purpose",
                f"A {expected_purpose} QR token is required.",
            )
        return claims
