"""Gate 1 QR and encounter application workflows."""

import secrets
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from jejakjkn_auth.jwt_verifier import Principal
from jejakjkn_canonical.problems import Problem

from app.api.schemas import ExceptionRequest, IssueQrRequest, RedeemQrRequest
from app.config import Settings
from app.domain.entities import EncounterStatus, PresenceStatus
from app.domain.policies import require_checkout_eligible
from app.infrastructure.crypto import QrSigner
from app.infrastructure.models import Encounter, EncounterException, OutboxEvent, QrRedemptionReceipt
from app.infrastructure.redis_qr import RedisQrStore, nonce_digest
from app.infrastructure.repositories import EncounterRepository


class EncounterApplication:
    def __init__(self, session: AsyncSession, qr_store: RedisQrStore, signer: QrSigner, settings: Settings) -> None:
        self.session = session
        self.repo = EncounterRepository(session)
        self.qr_store = qr_store
        self.signer = signer
        self.settings = settings

    async def issue_qr(self, request: IssueQrRequest, principal: Principal) -> dict:
        patient_id = _patient_id(principal)
        if not await self.repo.patient(patient_id):
            raise Problem(404, "PATIENT_NOT_FOUND", "Patient not found", "The authenticated patient is not provisioned.")
        if request.encounter_id:
            encounter = await self.repo.encounter(request.encounter_id)
            if not encounter or encounter.patient_id != patient_id:
                raise Problem(404, "ENCOUNTER_NOT_FOUND", "Encounter not found", "The encounter was not found.")
            require_checkout_eligible(encounter.status)
        nonce = secrets.token_urlsafe(24)
        token, expires_at = self.signer.issue(
            nonce=nonce,
            patient_id=patient_id,
            purpose=request.purpose,
            encounter_id=request.encounter_id,
            facility_hint=request.facility_hint,
        )
        await self.qr_store.issue(
            nonce=nonce,
            patient_id=str(patient_id),
            purpose=request.purpose,
            encounter_id=str(request.encounter_id) if request.encounter_id else None,
            facility_hint=request.facility_hint,
            ttl_seconds=self.settings.qr_token_ttl_seconds,
        )
        return {"token": token, "purpose": request.purpose, "expires_at": expires_at, "ttl_seconds": self.settings.qr_token_ttl_seconds}

    async def redeem(self, request: RedeemQrRequest, idempotency_key: str, principal: Principal, purpose: str) -> tuple[dict, bool]:
        if principal.organization_id is None:
            raise Problem(403, "TENANT_REQUIRED", "Forbidden", "The scanner credential is not bound to a facility.")
        claims = self.signer.verify(request.qr_token, purpose)
        nonce = claims["jti"]
        digest = nonce_digest(nonce)
        previous_key = await self.repo.receipt_by_idempotency(principal.client_id, idempotency_key)
        if previous_key:
            if previous_key.nonce_digest != digest:
                raise Problem(409, "IDEMPOTENCY_KEY_PAYLOAD_MISMATCH", "Idempotency conflict", "This idempotency key was already used for another QR token.")
            return previous_key.response_payload, True

        organization = await self.repo.organization("DEMO-FASKES", request.facility_external_code)
        if not organization or organization.id != principal.organization_id:
            raise Problem(403, "FACILITY_MISMATCH", "Facility mismatch", "The scanner credential is not authorized for this facility.")
        source_system = await self.repo.source_system(principal.client_id)
        if not source_system or source_system.organization_id != organization.id:
            raise Problem(403, "SOURCE_SYSTEM_FORBIDDEN", "Forbidden", "The scanner source system is disabled or belongs to another facility.")

        preallocated = UUID(claims["enc"]) if claims.get("enc") else uuid4()
        reservation = await self.qr_store.reserve(
            nonce=nonce,
            reservation_key=f"{principal.client_id}:{idempotency_key}",
            purpose=purpose,
            encounter_id=str(preallocated),
            facility_code=request.facility_external_code,
        )
        patient_id = UUID(claims["sub"])
        if reservation.patient_id != str(patient_id):
            raise Problem(401, "INVALID_QR_TOKEN", "Invalid QR token", "The QR token reservation does not match its signed subject.")
        encounter_id = UUID(reservation.encounter_id)

        existing = await self.repo.receipt(digest)
        if existing:
            if existing.scanner_client_id != principal.client_id or existing.idempotency_key != idempotency_key:
                raise Problem(409, "QR_ALREADY_CONSUMED", "QR token already consumed", "The QR token was redeemed by another request.")
            await self.qr_store.commit(nonce)
            return existing.response_payload, True

        try:
            now = datetime.now(UTC)
            if purpose == "CHECK_IN":
                encounter = Encounter(
                        id=encounter_id,
                        patient_id=patient_id,
                        organization_id=organization.id,
                        source_system_id=source_system.id,
                        external_visit_reference=request.external_visit_reference,
                        service_type="OUTPATIENT",
                        status=EncounterStatus.OPEN,
                        presence_status=PresenceStatus.QR_VERIFIED,
                        started_at=now,
                        created_by=principal.subject,
                    )
                self.session.add(encounter)
                response = {"encounter_id": str(encounter_id), "check_in_status": "QR_VERIFIED", "encounter_status": "OPEN", "created_at": now.isoformat()}
                event_type = "encounter.opened.v1"
            else:
                encounter = await self.repo.encounter_for_update(encounter_id)
                if not encounter or encounter.patient_id != patient_id or encounter.organization_id != organization.id:
                    raise Problem(404, "ENCOUNTER_NOT_FOUND", "Encounter not found", "The checkout encounter was not found.")
                require_checkout_eligible(encounter.status)
                encounter.status = EncounterStatus.CHECKED_OUT
                encounter.ended_at = now
                encounter.revision += 1
                response = {"encounter_id": str(encounter_id), "encounter_status": "CHECKED_OUT", "checked_out_at": now.isoformat()}
                event_type = "encounter.checked_out.v1"
            self.session.add(QrRedemptionReceipt(
                nonce_digest=digest,
                purpose=purpose,
                patient_id=patient_id,
                encounter_id=encounter_id,
                organization_id=organization.id,
                scanner_client_id=principal.client_id,
                scanner_external_id=request.scanner_external_id,
                idempotency_key=idempotency_key,
                response_payload=response,
            ))
            event_data = response | {"patient_id": str(patient_id), "presence_status": str(encounter.presence_status)}
            self.session.add(_outbox(event_type, encounter, principal.subject, event_data))
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            existing = await self.repo.receipt(digest)
            if not existing or existing.scanner_client_id != principal.client_id or existing.idempotency_key != idempotency_key:
                raise Problem(409, "QR_ALREADY_CONSUMED", "QR token already consumed", "The QR token was redeemed by another request.") from exc
            response = existing.response_payload
            await self.qr_store.commit(nonce)
            return response, True

        await self.qr_store.commit(nonce)
        return response, reservation.state == "IDEMPOTENT_RETRY"

    async def record_exception(self, encounter_id: UUID, request: ExceptionRequest, principal: Principal) -> dict:
        if principal.organization_id is None:
            raise Problem(403, "TENANT_REQUIRED", "Forbidden", "The credential is not bound to a facility.")
        organization = await self.repo.organization("DEMO-FASKES", request.facility_external_code)
        if not organization or organization.id != principal.organization_id:
            raise Problem(403, "FACILITY_MISMATCH", "Facility mismatch", "The caller is not authorized for this facility.")
        encounter = await self.repo.encounter(encounter_id)
        now = datetime.now(UTC)
        if encounter is None:
            if request.exception_phase != "CHECK_IN" or request.patient_id is None or not await self.repo.patient(request.patient_id):
                raise Problem(404, "ENCOUNTER_NOT_FOUND", "Encounter not found", "A CHECK_IN exception requires a provisioned patient.")
            encounter = Encounter(
                    id=encounter_id,
                    patient_id=request.patient_id,
                    organization_id=organization.id,
                    service_type=request.service_type,
                    status=EncounterStatus.OPEN,
                    presence_status=PresenceStatus.EXCEPTION_DOCUMENTED,
                    started_at=now,
                    created_by=principal.subject,
                )
            self.session.add(encounter)
        else:
            if encounter.organization_id != organization.id:
                raise Problem(404, "ENCOUNTER_NOT_FOUND", "Encounter not found", "The encounter was not found.")
            if request.exception_phase == "CHECK_OUT":
                require_checkout_eligible(encounter.status)
                encounter.status = EncounterStatus.CLOSED_WITH_EXCEPTION
                encounter.ended_at = now
                encounter.revision += 1
            encounter.presence_status = PresenceStatus.EXCEPTION_DOCUMENTED
        self.session.add(EncounterException(
            id=uuid4(), encounter_id=encounter.id, exception_phase=request.exception_phase,
            reason_code=request.reason_code, approved_by=request.approved_by,
            evidence_ref=request.evidence_ref, notes=request.notes,
        ))
        response = {"encounter_id": str(encounter.id), "encounter_status": str(encounter.status), "presence_status": "EXCEPTION_DOCUMENTED"}
        event_data = response | {"patient_id": str(encounter.patient_id), "checked_out_at": encounter.ended_at.isoformat() if encounter.ended_at else None}
        self.session.add(_outbox("encounter.exception_recorded.v1", encounter, principal.subject, event_data))
        await self.session.commit()
        return response


def _patient_id(principal: Principal) -> UUID:
    if principal.patient_id is None:
        raise Problem(403, "PATIENT_CONTEXT_REQUIRED", "Forbidden", "The token is not bound to a patient.")
    return principal.patient_id


def _outbox(event_type: str, encounter: Encounter, actor: str, data: dict) -> OutboxEvent:
    now = datetime.now(UTC)
    return OutboxEvent(
        event_id=uuid4(), event_type=event_type, aggregate_id=str(encounter.id), aggregate_revision=encounter.revision or 1,
        organization_id=str(encounter.organization_id), correlation_id=actor, payload=data, occurred_at=now,
    )
