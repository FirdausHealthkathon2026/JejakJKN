"""Gate 2 evidence ingestion and Gate 3 frozen patient summaries."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jejakjkn_auth.jwt_verifier import Principal
from jejakjkn_canonical.problems import Problem

from app.api.schemas import CancellationRequest, ClinicalEventRequest, CorrectionRequest, PatientResponseRequest, SyncCompleteRequest
from app.config import Settings
from app.domain.policies import VISIBLE_SUMMARY_KINDS, internal_kind, mapping_status
from app.infrastructure.crypto import encrypt_note
from app.infrastructure.models import CareStage, EvidenceOutbox, EvidenceQuarantine, EvidenceRecord, EvidenceVersion, PatientItemResponse, PatientResponse, SummarySnapshot
from app.infrastructure.repositories import EvidenceRepository

SOURCE_BY_CLIENT = {"simrs-a-adapter": "SIMRS-A", "simrs-b-adapter": "SIMRS-B"}


class EvidenceApplication:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.repo = EvidenceRepository(session)

    async def ingest(self, encounter_id: UUID, body: ClinicalEventRequest | CorrectionRequest | CancellationRequest, principal: Principal, action: str) -> tuple[dict, bool]:
        episode = await self._authorized_episode(encounter_id, principal, lock=True)
        self._require_source(principal, body.source_system)
        replay = await self.repo.version_by_event(encounter_id, body.source_event_id)
        if replay:
            if replay.payload_digest != _digest(body.model_dump(mode="json")):
                raise Problem(409, "SOURCE_EVENT_PAYLOAD_MISMATCH", "Source event conflict", "This source event ID was already used for another payload.")
            return self._write_response(episode.current_revision, replay, "IDEMPOTENT_REPLAY"), True
        quarantined = await self.repo.quarantine_by_event(episode.organization_id, body.source_system, body.source_event_id)
        if quarantined:
            if _digest(quarantined.raw_payload) != _digest(body.model_dump(mode="json")):
                raise Problem(409, "SOURCE_EVENT_PAYLOAD_MISMATCH", "Source event conflict", "This source event ID was already used for another payload.")
            return self._quarantine_response(episode.current_revision, quarantined), True
        if await self.repo.version_by_sequence(encounter_id, body.source_sequence):
            return await self._quarantine(episode, body, None)

        record = await self.repo.record(episode.organization_id, body.source_system, body.external_record_id, lock=True)
        if record and record.encounter_id != encounter_id:
            raise Problem(409, "EXTERNAL_RECORD_CONFLICT", "External record conflict", "This external record belongs to another encounter.")
        received_version = body.record_version
        if action == "RECORDED" and record is None:
            event_kind = internal_kind(body.event_type)
            record = EvidenceRecord(
                id=uuid4(), encounter_id=encounter_id, organization_id=episode.organization_id,
                source_system_id=body.source_system, external_record_id=body.external_record_id,
                kind=event_kind, current_version=1, status="ACTIVE",
            )
            self.session.add(record)
        elif record is None or received_version != record.current_version + 1 or action == "RECORDED":
            return await self._quarantine(episode, body, record.current_version if record else None)

        if action == "CANCELLED":
            previous = await self.repo.latest_version(record.id)
            if previous is None:
                return await self._quarantine(episode, body, record.current_version)
            content = {
                "code_system": previous.code_system, "code": previous.code, "display": previous.display_text,
                "quantity": previous.quantity, "unit": previous.unit,
            }
            occurred_at = body.source_updated_at
            source_updated_at = body.source_updated_at
            change_reason = body.cancel_reason
            stage_completion = previous.stage_completion
        else:
            content = body.content.model_dump(mode="json")
            occurred_at = body.occurred_at
            source_updated_at = getattr(body, "source_updated_at", None)
            change_reason = getattr(body, "change_reason", None)
            stage_completion = body.stage_completion

        payload = body.model_dump(mode="json")
        mapped = mapping_status(str(content["code_system"]))
        version = EvidenceVersion(
            id=uuid4(), evidence_id=record.id, encounter_id=encounter_id, version=received_version,
            source_event_id=body.source_event_id, source_sequence=body.source_sequence, event_action=action,
            code_system=str(content["code_system"]), code=str(content["code"]),
            canonical_code_system=str(content["code_system"]) if mapped == "MAPPED" else None,
            canonical_code=str(content["code"]) if mapped == "MAPPED" else None,
            mapping_status=mapped, display_text=str(content["display"]), quantity=content.get("quantity"),
            unit=content.get("unit"), canonical_quantity=content.get("quantity") if mapped == "MAPPED" else None,
            canonical_unit=content.get("unit") if mapped == "MAPPED" else None, stage_completion=stage_completion,
            source_actor_id=body.actor.external_id, source_actor_role=body.actor.role, change_reason=change_reason,
            payload=payload, payload_digest=_digest(payload), occurred_at=occurred_at, source_updated_at=source_updated_at,
        )
        self.session.add(version)
        record.current_version = received_version
        record.status = "CANCELLED" if action == "CANCELLED" else "CORRECTED" if action == "CORRECTED" else "ACTIVE"
        episode.current_revision += 1
        if record.kind == "STAGE_COMPLETION" and action != "CANCELLED":
            self.session.add(CareStage(id=uuid4(), encounter_id=encounter_id, stage_type=version.code, status=stage_completion or "STAFF_COMPLETED", source_ref=body.external_record_id, completed_at=occurred_at))
        await self.session.flush()
        episode.last_acked_source_sequence = _contiguous(await self.repo.sequences(encounter_id))
        if episode.sync_status == "SYNC_COMPLETE":
            await self._invalidate_previous_snapshot(encounter_id)
            episode.sync_status = "RECEIVING"
            episode.expected_final_sequence = None
            episode.sync_completed_at = None
        self.session.add(_outbox(f"evidence.{action.lower()}.v1", episode, {"evidence_id": str(record.id), "evidence_version_id": str(version.id), "kind": record.kind}))
        await self.session.commit()
        return self._write_response(episode.current_revision, version, record.status), False

    async def mark_sync_complete(self, encounter_id: UUID, body: SyncCompleteRequest, principal: Principal) -> dict:
        episode = await self._authorized_episode(encounter_id, principal, lock=True)
        self._require_source(principal, body.source_system)
        episode.last_acked_source_sequence = _contiguous(await self.repo.sequences(encounter_id))
        episode.expected_final_sequence = body.last_source_sequence
        quarantined = await self.repo.has_unresolved_quarantine(encounter_id)
        complete = episode.last_acked_source_sequence == body.last_source_sequence and not quarantined
        episode.sync_status = "SYNC_COMPLETE" if complete else "QUARANTINE_PENDING" if quarantined else "INCOMPLETE_SYNC"
        episode.sync_completed_at = body.marked_complete_at if complete else None
        snapshot = await self._build_snapshot(episode) if episode.checked_out_at else None
        await self.session.commit()
        return self._sync_response(episode, snapshot)

    async def ingestion_status(self, encounter_id: UUID, principal: Principal) -> dict:
        episode = await self._authorized_episode(encounter_id, principal)
        snapshot = await self.repo.latest_snapshot(encounter_id)
        return self._sync_response(episode, snapshot)

    async def checkout_summary(self, encounter_id: UUID, principal: Principal) -> dict:
        patient_id = _patient_id(principal)
        episode = await self.repo.episode(encounter_id)
        if not episode or episode.patient_id != patient_id:
            raise Problem(404, "CHECKOUT_SUMMARY_NOT_FOUND", "Checkout summary not found", "The checkout summary was not found.")
        if episode.checked_out_at is None:
            raise Problem(409, "ENCOUNTER_NOT_CHECKED_OUT", "Summary unavailable", "The encounter has not been checked out.")
        snapshot = await self.repo.latest_snapshot(encounter_id)
        if episode.sync_status != "SYNC_COMPLETE" or not snapshot or snapshot.status != "READY":
            status = snapshot.status if snapshot else "INCOMPLETE_SYNC"
            raise Problem(409, f"CHECKOUT_SUMMARY_{status}", "Summary not ready", "Waiting for the explicit SIMRS sync-complete watermark.")
        if snapshot.presented_at is None:
            snapshot.presented_at = datetime.now(UTC)
            await self.session.commit()
        return _summary(snapshot, include_items=True)

    async def submit_response(self, snapshot_id: UUID, body: PatientResponseRequest, idempotency_key: str, principal: Principal) -> tuple[dict, bool]:
        patient_id = _patient_id(principal)
        request_payload = body.model_dump(mode="json")
        request_digest = _digest(request_payload)
        existing = await self.repo.response_by_idempotency(idempotency_key)
        if existing:
            if existing.request_digest != request_digest or existing.patient_id != patient_id or existing.snapshot_id != snapshot_id:
                raise Problem(409, "IDEMPOTENCY_KEY_PAYLOAD_MISMATCH", "Idempotency conflict", "This idempotency key was already used for another response.")
            snapshot = await self.repo.snapshot(existing.snapshot_id)
            return _response(existing, snapshot.status), True

        snapshot = await self.repo.snapshot(snapshot_id, lock=True)
        if not snapshot:
            raise Problem(404, "CHECKOUT_SUMMARY_NOT_FOUND", "Checkout summary not found", "The checkout summary was not found.")
        episode = await self.repo.episode(snapshot.encounter_id, lock=True)
        if not episode or episode.patient_id != patient_id:
            raise Problem(404, "CHECKOUT_SUMMARY_NOT_FOUND", "Checkout summary not found", "The checkout summary was not found.")
        latest = await self.repo.latest_snapshot(snapshot.encounter_id)
        if snapshot.status != "READY" or not latest or latest.id != snapshot.id:
            raise Problem(409, "SNAPSHOT_NOT_CONFIRMABLE", "Snapshot not confirmable", "Only the latest READY snapshot can be confirmed.")
        if await self.repo.response_for_snapshot(snapshot.id):
            raise Problem(409, "SNAPSHOT_ALREADY_RESPONDED", "Response already recorded", "This snapshot already has a patient response.")

        expected = {UUID(item["evidence_id"]): item for item in snapshot.items_json}
        supplied = {item.evidence_id: item for item in body.items}
        if body.overall_response != "DECLINED" and (set(supplied) != set(expected) or len(body.items) != len(expected)):
            raise Problem(422, "ITEM_RESPONSE_SET_MISMATCH", "Invalid item responses", "Every frozen snapshot item must be answered exactly once.")
        response = PatientResponse(
            id=uuid4(), snapshot_id=snapshot.id, encounter_id=snapshot.encounter_id, patient_id=patient_id,
            response_type=body.overall_response, idempotency_key=idempotency_key, request_digest=request_digest,
        )
        self.session.add(response)
        await self.session.flush()
        for evidence_id, item in supplied.items():
            frozen = expected[evidence_id]
            self.session.add(PatientItemResponse(
                id=uuid4(), response_id=response.id, evidence_id=evidence_id,
                evidence_version_id=UUID(frozen["evidence_version_id"]), result=item.response,
                reason_code=item.reason,
                note_ciphertext=encrypt_note(item.note, self.settings.field_encryption_master_key, f"patient_item_responses:{response.id}:{evidence_id}:v1") if item.note else None,
            ))
        self.session.add(_outbox("patient.confirmation_recorded.v1", episode, {"response_id": str(response.id), "snapshot_id": str(snapshot.id), "response_type": response.response_type}))
        await self.session.commit()
        return _response(response, snapshot.status), False

    async def get_response(self, snapshot_id: UUID, principal: Principal) -> dict:
        patient_id = _patient_id(principal)
        snapshot = await self.repo.snapshot(snapshot_id)
        if not snapshot:
            raise Problem(404, "PATIENT_RESPONSE_NOT_FOUND", "Response not found", "No response was found.")
        episode = await self.repo.episode(snapshot.encounter_id)
        response = await self.repo.response_for_snapshot(snapshot_id)
        if not episode or episode.patient_id != patient_id or not response:
            raise Problem(404, "PATIENT_RESPONSE_NOT_FOUND", "Response not found", "No response was found.")
        return _response(response, snapshot.status)

    async def mark_expired_no_responses(self, now: datetime) -> int:
        cutoff = now - timedelta(hours=self.settings.patient_response_window_hours)
        rows = await self.repo.expired_unanswered_snapshots(cutoff)
        for snapshot, episode in rows:
            response = PatientResponse(
                id=uuid4(), snapshot_id=snapshot.id, encounter_id=episode.encounter_id, patient_id=episode.patient_id,
                response_type="NO_RESPONSE", method="SYSTEM_TIMEOUT", idempotency_key=f"timeout:{snapshot.id}", request_digest=_digest({"snapshot_id": str(snapshot.id), "response": "NO_RESPONSE"}),
            )
            self.session.add(response)
            self.session.add(_outbox("patient.confirmation_recorded.v1", episode, {"response_id": str(response.id), "snapshot_id": str(snapshot.id), "response_type": "NO_RESPONSE"}))
        await self.session.commit()
        return len(rows)

    async def _authorized_episode(self, encounter_id: UUID, principal: Principal, *, lock: bool = False):
        if principal.organization_id is None:
            raise Problem(403, "TENANT_REQUIRED", "Forbidden", "The credential is not bound to a facility.")
        episode = await self.repo.episode(encounter_id, lock=lock)
        if not episode:
            raise Problem(409, "CARE_EPISODE_NOT_READY", "Encounter not ready", "The encounter event has not reached the Evidence Service yet; retry safely.")
        if episode.organization_id != principal.organization_id:
            raise Problem(404, "CARE_EPISODE_NOT_FOUND", "Encounter not found", "The encounter was not found.")
        return episode

    @staticmethod
    def _require_source(principal: Principal, source_system: str) -> None:
        if SOURCE_BY_CLIENT.get(principal.client_id) != source_system:
            raise Problem(403, "SOURCE_SYSTEM_FORBIDDEN", "Forbidden", "The source system does not match the authenticated adapter.")

    async def _quarantine(self, episode, body, current_version: int | None) -> tuple[dict, bool]:
        quarantine = EvidenceQuarantine(
            id=uuid4(), organization_id=episode.organization_id, encounter_id=episode.encounter_id,
            source_system=body.source_system, source_event_id=body.source_event_id,
            external_record_id=body.external_record_id, received_version=body.record_version,
            current_known_version=current_version, reason_code="OUT_OF_ORDER_VERSION", raw_payload=body.model_dump(mode="json"),
        )
        self.session.add(quarantine)
        await self._invalidate_previous_snapshot(episode.encounter_id)
        episode.sync_status = "QUARANTINE_PENDING"
        episode.expected_final_sequence = None
        episode.sync_completed_at = None
        await self.session.commit()
        return {"evidence_id": None, "evidence_version_id": None, "record_version": body.record_version, "encounter_evidence_revision": episode.current_revision, "status": "QUARANTINED", "mapping_status": None}, False

    @staticmethod
    def _quarantine_response(revision: int, quarantine: EvidenceQuarantine) -> dict:
        return {"evidence_id": None, "evidence_version_id": None, "record_version": quarantine.received_version, "encounter_evidence_revision": revision, "status": "QUARANTINED", "mapping_status": None}

    async def _invalidate_previous_snapshot(self, encounter_id: UUID) -> None:
        snapshot = await self.repo.latest_snapshot(encounter_id)
        if not snapshot or snapshot.status != "READY":
            return
        response = await self.repo.response_for_snapshot(snapshot.id)
        snapshot.status = "RECONFIRMATION_REQUIRED" if response else "OUTDATED"

    async def _build_snapshot(self, episode) -> SummarySnapshot:
        ready = episode.sync_status == "SYNC_COMPLETE" and episode.expected_final_sequence == episode.last_acked_source_sequence
        items = []
        if ready:
            for record, version in await self.repo.current_versions(episode.encounter_id):
                if record.kind not in VISIBLE_SUMMARY_KINDS:
                    continue
                items.append({
                    "evidence_id": str(record.id), "evidence_version_id": str(version.id), "version": version.version,
                    "kind": record.kind, "description": version.display_text,
                    "quantity": str(version.quantity) if version.quantity is not None else None,
                    "unit": version.unit, "recorded_status": version.stage_completion or "STAFF_COMPLETED",
                })
        status = "READY" if ready else "INCOMPLETE_SYNC"
        digest = _digest(items)
        latest = await self.repo.latest_snapshot(episode.encounter_id)
        publish_ready = False
        if latest and latest.evidence_revision == episode.current_revision and latest.presented_at is None and not await self.repo.response_for_snapshot(latest.id):
            publish_ready = ready and latest.status != "READY"
            latest.status, latest.items_json, latest.content_digest = status, items, digest
            snapshot = latest
        elif latest and latest.evidence_revision == episode.current_revision:
            return latest
        else:
            snapshot = SummarySnapshot(id=uuid4(), encounter_id=episode.encounter_id, evidence_revision=episode.current_revision, status=status, items_json=items, content_digest=digest)
            self.session.add(snapshot)
            await self.session.flush()
            publish_ready = ready
        if publish_ready:
            prior = await self.session.scalar(select(SummarySnapshot).where(SummarySnapshot.encounter_id == episode.encounter_id, SummarySnapshot.id != snapshot.id, SummarySnapshot.status == "RECONFIRMATION_REQUIRED").order_by(SummarySnapshot.created_at.desc()).limit(1))
            if prior:
                response = await self.repo.response_for_snapshot(prior.id)
                if response:
                    response.superseded_by_snapshot_id = snapshot.id
            self.session.add(_outbox("patient.summary_ready.v1", episode, {"snapshot_id": str(snapshot.id), "evidence_revision": episode.current_revision}))
        return snapshot

    @staticmethod
    def _write_response(revision: int, version: EvidenceVersion, status: str) -> dict:
        return {"evidence_id": version.evidence_id, "evidence_version_id": version.id, "record_version": version.version, "encounter_evidence_revision": revision, "status": status, "mapping_status": version.mapping_status}

    @staticmethod
    def _sync_response(episode, snapshot: SummarySnapshot | None) -> dict:
        return {"encounter_id": episode.encounter_id, "sync_status": episode.sync_status, "current_revision": episode.current_revision, "last_acked_source_sequence": episode.last_acked_source_sequence, "expected_final_sequence": episode.expected_final_sequence, "snapshot_id": snapshot.id if snapshot else None}


def _patient_id(principal: Principal) -> UUID:
    if principal.patient_id is None:
        raise Problem(403, "PATIENT_CONTEXT_REQUIRED", "Forbidden", "The token is not bound to a patient.")
    return principal.patient_id


def _contiguous(values: list[int]) -> int:
    expected = 1
    for value in values:
        if value != expected:
            break
        expected += 1
    return expected - 1


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _outbox(event_type: str, episode, payload: dict) -> EvidenceOutbox:
    now = datetime.now(UTC)
    return EvidenceOutbox(event_id=uuid4(), event_type=event_type, aggregate_id=str(episode.encounter_id), aggregate_revision=max(episode.current_revision, 1), organization_id=str(episode.organization_id), correlation_id=str(episode.encounter_id), payload=payload, occurred_at=now)


def _summary(snapshot: SummarySnapshot, *, include_items: bool) -> dict:
    return {"snapshot_id": snapshot.id, "encounter_id": snapshot.encounter_id, "status": snapshot.status, "evidence_revision": snapshot.evidence_revision, "presented_at": snapshot.presented_at, "items": snapshot.items_json if include_items else []}


def _response(response: PatientResponse, snapshot_status: str) -> dict:
    return {"response_id": response.id, "snapshot_id": response.snapshot_id, "overall_response": response.response_type, "submitted_at": response.submitted_at, "snapshot_status": snapshot_status}
