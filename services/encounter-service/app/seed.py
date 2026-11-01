"""Idempotent Gate 1 synthetic organization, patient, and scanner seed."""

import asyncio
import hashlib
import hmac
from uuid import UUID

from app.config import get_settings
from app.infrastructure.crypto import blind_index, encrypt_field
from app.infrastructure.db import SessionFactory
from app.infrastructure.models import Organization, Patient, SourceSystem

ORGANIZATIONS = (
    (
        UUID("00000000-0000-4000-8000-000000000001"),
        "HOSP-DEMO-001",
        "RS Demo Satu",
        "FASKES",
    ),
    (
        UUID("00000000-0000-4000-8000-000000000002"),
        "HOSP-DEMO-002",
        "RS Demo Dua",
        "FASKES",
    ),
    (
        UUID("00000000-0000-4000-8000-000000000003"),
        "VERIFIER-DEMO",
        "Verifier Demo",
        "VERIFIER_ORG",
    ),
)


async def seed() -> None:
    settings = get_settings()
    async with SessionFactory() as session:
        for org_id, code, name, org_type in ORGANIZATIONS:
            if not await session.get(Organization, org_id):
                session.add(
                    Organization(
                        id=org_id,
                        code_namespace="DEMO-FASKES"
                        if org_type == "FASKES"
                        else "DEMO-VERIFIER",
                        external_code=code,
                        display_name=name,
                        org_type=org_type,
                    )
                )
        await session.flush()
        sources = (
            (
                UUID("20000000-0000-4000-8000-000000000001"),
                ORGANIZATIONS[0][0],
                "simrs-a-adapter",
                "SIMRS-A",
            ),
            (
                UUID("20000000-0000-4000-8000-000000000002"),
                ORGANIZATIONS[1][0],
                "simrs-b-adapter",
                "SIMRS-B",
            ),
        )
        for source_id, org_id, client_id, source_code in sources:
            if not await session.get(SourceSystem, source_id):
                session.add(
                    SourceSystem(
                        id=source_id,
                        organization_id=org_id,
                        client_id=client_id,
                        source_code=source_code,
                        kind="SIMRS_ADAPTER",
                    )
                )
        for number in range(1, 21):
            patient_id = UUID(f"10000000-0000-4000-8000-{number:012d}")
            if await session.get(Patient, patient_id):
                continue
            participant = f"SYNTHETIC-{10000 + number}"
            name = (
                "Nama Kembar" if number in {1, 2} else f"Pasien Sintetis {number:02d}"
            )
            session.add(
                Patient(
                    id=patient_id,
                    participant_lookup_key=blind_index(
                        participant, settings.participant_lookup_hmac_key
                    ),
                    participant_number_ciphertext=encrypt_field(
                        participant,
                        settings.field_encryption_master_key,
                        f"patients:{patient_id}:participant_number_ciphertext:v1",
                    ),
                    display_name_ciphertext=encrypt_field(
                        name,
                        settings.field_encryption_master_key,
                        f"patients:{patient_id}:display_name_ciphertext:v1",
                    ),
                    display_name_normalized_hmac=hmac.new(
                        bytes.fromhex(settings.participant_lookup_hmac_key),
                        name.strip().lower().encode(),
                        hashlib.sha256,
                    ).hexdigest(),
                    identity_assurance="VERIFIED_PARTICIPANT_ID",
                )
            )
        await session.commit()
    print(
        "[seed] Gate 1 synthetic organizations, source systems, and 20 patients are ready"
    )


if __name__ == "__main__":
    asyncio.run(seed())
