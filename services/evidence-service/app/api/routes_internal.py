"""Immutable evidence snapshots for trusted verification workers."""

import hashlib
import json
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from jejakjkn_auth.dependencies import principal_dependency, require_roles
from jejakjkn_auth.jwt_verifier import Principal
from jejakjkn_canonical.problems import Problem

from app.config import get_settings
from app.infrastructure.db import get_session
from app.infrastructure.models import VerificationEvidenceSnapshot
from app.infrastructure.repositories import EvidenceRepository

from .schemas import VerificationSnapshotView

settings = get_settings()
internal_principal = require_roles(principal_dependency(settings.keycloak_issuer_url, settings.jwt_audience, settings.keycloak_jwks_url), "internal_service")
router = APIRouter(prefix="/internal/v1")


@router.post("/encounters/{encounter_id}/evidence-snapshots", response_model=VerificationSnapshotView, status_code=201)
async def pin_snapshot(encounter_id: UUID, _: Principal = Depends(internal_principal), session: AsyncSession = Depends(get_session)) -> dict:
    repo = EvidenceRepository(session)
    episode = await repo.episode(encounter_id, lock=True)
    if not episode:
        raise Problem(404, "CARE_EPISODE_NOT_FOUND", "Encounter not found", "The evidence episode was not found.")
    summary = await repo.latest_snapshot(encounter_id)
    response = await repo.response_for_snapshot(summary.id) if summary else None
    item_responses = {row.evidence_id: row.result for row in await repo.item_responses(response.id)} if response else {}
    confirmation = "SNAPSHOT_OUTDATED" if summary and summary.status != "READY" and response else response.response_type if response else "NOT_APPLICABLE"
    items = [
        {
            "evidence_id": str(record.id), "evidence_version_id": str(version.id), "version": version.version,
            "kind": record.kind, "status": record.status, "code_system": version.code_system, "code": version.code,
            "canonical_code_system": version.canonical_code_system, "canonical_code": version.canonical_code,
            "mapping_status": version.mapping_status, "description": version.display_text,
            "quantity": str(version.quantity) if version.quantity is not None else None, "unit": version.unit,
            "canonical_quantity": str(version.canonical_quantity) if version.canonical_quantity is not None else None,
            "canonical_unit": version.canonical_unit, "occurred_at": version.occurred_at.isoformat(),
            "recorded_at": version.recorded_at.isoformat(), "patient_response": item_responses.get(record.id),
        }
        for record, version in await repo.all_current_versions(encounter_id)
    ]
    attestation = {"summary_snapshot_id": str(summary.id) if summary else None, "summary_status": summary.status if summary else "NOT_AVAILABLE", "response_id": str(response.id) if response else None, "response_type": response.response_type if response else None, "checked_out_at": episode.checked_out_at.isoformat() if episode.checked_out_at else None}
    digest = hashlib.sha256(json.dumps({"revision": episode.current_revision, "sync": episode.sync_status, "items": items, "attestation": attestation}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    snapshot = await repo.verification_snapshot_by_digest(encounter_id, episode.current_revision, digest)
    if not snapshot:
        snapshot = VerificationEvidenceSnapshot(
            id=uuid4(), encounter_id=encounter_id, evidence_revision=episode.current_revision,
            episode_sync_status=episode.sync_status, presence_status=episode.presence_status,
            patient_confirmation_status=confirmation, pinned_items_json=items,
            pinned_attestation_json=attestation, content_digest=digest,
        )
        session.add(snapshot)
        await session.commit()
    return _view(snapshot)


@router.get("/evidence-snapshots/{snapshot_id}", response_model=VerificationSnapshotView)
async def get_snapshot(snapshot_id: UUID, _: Principal = Depends(internal_principal), session: AsyncSession = Depends(get_session)) -> dict:
    snapshot = await EvidenceRepository(session).verification_snapshot(snapshot_id)
    if not snapshot:
        raise Problem(404, "EVIDENCE_SNAPSHOT_NOT_FOUND", "Snapshot not found", "The evidence snapshot was not found.")
    return _view(snapshot)


def _view(snapshot: VerificationEvidenceSnapshot) -> dict:
    return {
        "snapshot_id": snapshot.id, "encounter_id": snapshot.encounter_id,
        "evidence_revision": snapshot.evidence_revision, "episode_sync_status": snapshot.episode_sync_status,
        "presence_status": snapshot.presence_status, "patient_confirmation_status": snapshot.patient_confirmation_status,
        "content_digest": snapshot.content_digest, "items": snapshot.pinned_items_json,
        "attestation": snapshot.pinned_attestation_json,
    }
