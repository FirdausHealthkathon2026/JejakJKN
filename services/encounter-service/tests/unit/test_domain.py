from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)
from pydantic import ValidationError

from app.api.schemas import IssueQrRequest
from app.application.use_cases import _outbox
from app.domain.policies import require_checkout_eligible
from app.infrastructure.crypto import QrSigner, blind_index, encrypt_field
from app.infrastructure.models import Encounter
from app.infrastructure.redis_qr import RedisQrStore
from jejakjkn_canonical.problems import Problem
from redis.exceptions import ConnectionError


@pytest.fixture
def signer(tmp_path: Path) -> QrSigner:
    private = Ed25519PrivateKey.generate()
    private_path = tmp_path / "private.pem"
    public_path = tmp_path / "public.pem"
    private_path.write_bytes(
        private.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
    )
    public_path.write_bytes(
        private.public_key().public_bytes(
            Encoding.PEM, PublicFormat.SubjectPublicKeyInfo
        )
    )
    return QrSigner(private_path, public_path, "test", 60)


def test_checkout_qr_requires_encounter() -> None:
    with pytest.raises(ValidationError):
        IssueQrRequest(purpose="CHECK_OUT")


def test_only_open_encounter_can_checkout() -> None:
    require_checkout_eligible("OPEN")
    with pytest.raises(Problem) as error:
        require_checkout_eligible("CHECKED_OUT")
    assert error.value.code == "INVALID_ENCOUNTER_STATE"


def test_new_encounter_outbox_starts_at_revision_one() -> None:
    encounter = Encounter(id=uuid4(), patient_id=uuid4(), organization_id=uuid4())
    assert (
        _outbox("encounter.opened.v1", encounter, "actor", {}).aggregate_revision == 1
    )


def test_qr_is_signed_short_lived_and_contains_no_phi(signer: QrSigner) -> None:
    patient_id = uuid4()
    token, expires_at = signer.issue(
        nonce="nonce",
        patient_id=patient_id,
        purpose="CHECK_IN",
        encounter_id=None,
        facility_hint="HOSP-DEMO-001",
    )
    claims = signer.verify(token, "CHECK_IN")
    assert claims["sub"] == str(patient_id)
    assert expires_at <= datetime.now(UTC) + timedelta(seconds=61)
    assert set(claims) >= {"iss", "aud", "jti", "sub", "pur", "iat", "exp"}
    assert "name" not in claims and "participant_number" not in claims


def test_tampered_qr_is_rejected(signer: QrSigner) -> None:
    token, _ = signer.issue(
        nonce="nonce",
        patient_id=uuid4(),
        purpose="CHECK_IN",
        encounter_id=None,
        facility_hint=None,
    )
    header, payload, signature = token.split(".")
    payload = ("A" if payload[0] != "A" else "B") + payload[1:]
    tampered = ".".join((header, payload, signature))
    with pytest.raises(Problem) as error:
        signer.verify(tampered, "CHECK_IN")
    assert error.value.code == "INVALID_QR_SIGNATURE"


def test_expired_qr_is_rejected(signer: QrSigner) -> None:
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "iss": signer.issuer,
            "aud": signer.audience,
            "jti": "old",
            "sub": str(uuid4()),
            "pur": "CHECK_IN",
            "iat": now - timedelta(minutes=2),
            "exp": now - timedelta(minutes=1),
        },
        signer.private_key,
        algorithm="EdDSA",
    )
    with pytest.raises(Problem) as error:
        signer.verify(token, "CHECK_IN")
    assert error.value.code == "QR_TOKEN_EXPIRED"


def test_blind_index_normalizes_and_encryption_is_randomized() -> None:
    key = "11" * 32
    assert blind_index(" synthetic-10001 ", key) == blind_index("SYNTHETIC-10001", key)
    first = encrypt_field("SYNTHETIC-10001", "22" * 32, "patients:id:participant:v1")
    second = encrypt_field("SYNTHETIC-10001", "22" * 32, "patients:id:participant:v1")
    assert first != second


@pytest.mark.asyncio
async def test_redis_outage_fails_closed() -> None:
    class BrokenRedis:
        def pipeline(self, transaction: bool):
            raise ConnectionError("offline")

    store = RedisQrStore(BrokenRedis())
    with pytest.raises(Problem) as error:
        await store.issue(
            nonce="n",
            patient_id=str(uuid4()),
            purpose="CHECK_IN",
            encounter_id=None,
            facility_hint=None,
            ttl_seconds=60,
        )
    assert error.value.status == 503
