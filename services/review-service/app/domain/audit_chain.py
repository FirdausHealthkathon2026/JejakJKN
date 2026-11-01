"""Small deterministic tamper-evident hash chain primitives."""

import hashlib
import json
from datetime import datetime
from typing import Any


GENESIS = "0" * 64


def digest_payload(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def record_hash(
    partition: str,
    previous: str,
    record_id: str,
    payload_digest: str,
    created_at: datetime,
) -> str:
    material = "|".join(
        (partition, previous, record_id, payload_digest, created_at.isoformat())
    )
    return hashlib.sha256(material.encode()).hexdigest()


def verify_chain(rows: list[Any]) -> bool:
    previous = GENESIS
    for row in rows:
        if row.previous_hash != previous or row.record_hash != record_hash(
            row.partition_key,
            previous,
            str(row.record_id),
            row.payload_digest,
            row.created_at,
        ):
            return False
        previous = row.record_hash
    return True
