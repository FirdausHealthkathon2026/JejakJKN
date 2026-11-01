from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from app.domain.audit_chain import GENESIS, digest_payload, record_hash, verify_chain


def test_hash_chain_detects_tampering() -> None:
    created = datetime.now(UTC)
    record_id = uuid4()
    digest = digest_payload({"decision": "ESCALATE"})
    row = SimpleNamespace(
        partition_key="org",
        previous_hash=GENESIS,
        record_id=record_id,
        payload_digest=digest,
        created_at=created,
        record_hash=record_hash("org", GENESIS, str(record_id), digest, created),
    )
    assert verify_chain([row])
    row.payload_digest = "f" * 64
    assert not verify_chain([row])
