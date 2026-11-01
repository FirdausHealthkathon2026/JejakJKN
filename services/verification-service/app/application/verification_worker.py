"""Execute queued verification runs against pinned internal snapshots."""

import asyncio
import hashlib
import json
import logging
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select, text

from app.config import get_settings
from app.domain.reconciliation import classify_candidates, reconcile_items
from app.domain.rules_engine import evaluate_rules
from app.infrastructure.db import SessionFactory
from app.infrastructure.internal_clients import InternalClients
from app.infrastructure.models import (
    CandidateEvaluation,
    ClaimEncounterAssociation,
    ClaimEvidenceAssociation,
    ItemEvaluation,
    RuleFinding,
    VerificationOutbox,
    VerificationRequest,
    VerificationRun,
)
from app.infrastructure.repositories import VerificationRepository

logger = logging.getLogger(__name__)


async def process_one() -> bool:
    async with SessionFactory() as session:
        run = await session.scalar(
            select(VerificationRun)
            .where(VerificationRun.status == "QUEUED")
            .order_by(VerificationRun.started_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if not run:
            return False
        run.status = "RUNNING"
        await session.commit()
        run_id = run.id
    try:
        await execute(run_id)
    except Exception as exc:
        logger.exception("verification run %s failed", run_id)
        async with SessionFactory() as session:
            run = await session.get(VerificationRun, run_id)
            run.status, run.error_detail, run.ended_at = (
                "FAILED",
                str(exc)[:1000],
                datetime.now(UTC),
            )
            request = await session.get(VerificationRequest, run.request_id)
            request.request_status = "FAILED"
            await session.commit()
    return True


async def execute(run_id: UUID) -> None:
    settings, clients = get_settings(), InternalClients(get_settings())
    async with SessionFactory() as session:
        run = await session.get(VerificationRun, run_id)
        request = await session.get(VerificationRequest, run.request_id)
        claim_items = [
            _item_dict(row)
            for row in await VerificationRepository(session).items(request.id)
        ]
        identity_key = (
            {"participant_lookup_key": request.participant_lookup_key}
            if request.participant_lookup_key
            else {"patient_name_hmac": request.patient_name_hmac}
        )
        search = await clients.search_candidates(
            identity_key
            | {
                "facility_namespace": request.facility_namespace,
                "facility_code": request.facility_code,
                "service_period_start": request.service_period_start.isoformat(),
                "service_period_end": request.service_period_end.isoformat(),
                "safety_limit": 10,
            }
        )
        evaluated: list[dict] = []
        all_snapshots: list[dict] = []
        for candidate in search["candidates"]:
            snapshot = None
            if candidate.get("status") in {"CHECKED_OUT", "CLOSED_WITH_EXCEPTION"}:
                # Checkout reaches Evidence through the durable outbox and may lag during batch processing or recovery.
                for _ in range(40):
                    snapshot = await clients.pin_snapshot(candidate["encounter_id"])
                    if snapshot.get("attestation", {}).get("checked_out_at"):
                        break
                    await asyncio.sleep(0.25)
                else:
                    snapshot = await clients.pin_snapshot(candidate["encounter_id"])
            else:
                snapshot = await clients.pin_snapshot(candidate["encounter_id"])

            if not snapshot.get("attestation", {}).get("checked_out_at"):
                state = "REJECTED_ABSENT_CHECKOUT"
                item_results = reconcile_items(claim_items, snapshot.get("items", []))
            else:
                item_results = reconcile_items(claim_items, snapshot["items"])
                matched = sum(item["match_result"] == "MATCHED" for item in item_results)
                state = (
                    "ELIGIBLE_COMPLETE_MATCH"
                    if matched == len(claim_items)
                    else "ELIGIBLE_PARTIAL_MATCH"
                    if matched
                    else "REJECTED_ITEM_MISMATCH"
                )
                if not request.participant_lookup_key:
                    state = "REJECTED_IDENTITY_WEAK"
            evaluated.append(
                {
                    "candidate": candidate,
                    "snapshot": snapshot,
                    "item_results": item_results,
                    "match_state": state,
                }
            )
            all_snapshots.append(
                {
                    "encounter_id": candidate["encounter_id"],
                    "encounter_revision": candidate["revision"],
                    "snapshot_id": snapshot["snapshot_id"],
                    "digest": snapshot["content_digest"],
                }
            )
        match_status, selected = classify_candidates(
            evaluated,
            truncated=search["truncated_by_limit"],
            strong_identity=bool(request.participant_lookup_key),
        )
        snapshot_digest = _digest(
            {
                "claim": request.claim_digest,
                "dependencies": all_snapshots,
                "rules": settings.ruleset_version,
                "mapping": settings.mapping_version,
            }
        )
        candidate_ids = [UUID(item["candidate"]["encounter_id"]) for item in evaluated]
        association_dependencies = []
        if candidate_ids:
            associations = (
                await session.scalars(
                    select(ClaimEncounterAssociation).where(
                        ClaimEncounterAssociation.encounter_id.in_(candidate_ids),
                        ClaimEncounterAssociation.status == "MATCHED",
                        ~(
                            (
                                ClaimEncounterAssociation.claim_source
                                == request.claim_source
                            )
                            & (ClaimEncounterAssociation.claim_id == request.claim_id)
                        ),
                    )
                )
            ).all()
            association_dependencies = sorted(
                f"{row.id}:{row.status}:{row.claim_source}:{row.claim_id}"
                for row in associations
            )
        dependency_fingerprint = _digest(
            {
                "dependencies": all_snapshots,
                "associations": association_dependencies,
                "rules": settings.ruleset_version,
                "mapping": settings.mapping_version,
            }
        )
        cached = await session.scalar(
            select(VerificationRun)
            .join(
                VerificationRequest,
                VerificationRequest.id == VerificationRun.request_id,
            )
            .where(
                VerificationRun.id != run.id,
                VerificationRun.status == "COMPLETED",
                VerificationRun.data_freshness == "CURRENT",
                VerificationRun.dependency_fingerprint == dependency_fingerprint,
                VerificationRequest.verifier_org_id == request.verifier_org_id,
                VerificationRequest.claim_source == request.claim_source,
                VerificationRequest.claim_id == request.claim_id,
                VerificationRequest.claim_digest == request.claim_digest,
            )
            .order_by(VerificationRun.ended_at.desc())
        )
        if cached and run.run_number == 1:
            request.latest_run_id, request.request_status = cached.id, "COMPLETED"
            await session.delete(run)
            session.add(
                VerificationOutbox(
                    event_id=uuid4(),
                    event_type="verification.completed.v1",
                    aggregate_id=str(cached.id),
                    aggregate_revision=cached.run_number,
                    organization_id=str(request.verifier_org_id),
                    correlation_id=str(request.id),
                    causation_id=None,
                    payload={
                        "verification_id": str(request.id),
                        "run_id": str(cached.id),
                        "cache_reused": True,
                    },
                    occurred_at=datetime.now(UTC),
                )
            )
            await session.commit()
            return
        for entry in evaluated:
            candidate, snapshot = entry["candidate"], entry["snapshot"]
            document_fingerprints = [
                item["code"]
                for item in snapshot["items"]
                if item["kind"] == "DOCUMENT_FINGERPRINT"
                and item["status"] in {"ACTIVE", "CORRECTED"}
            ]
            session.add(
                CandidateEvaluation(
                    id=uuid4(),
                    run_id=run.id,
                    encounter_id=UUID(candidate["encounter_id"]),
                    evidence_snapshot_id=UUID(snapshot["snapshot_id"]),
                    encounter_revision=candidate["revision"],
                    evidence_revision=snapshot["evidence_revision"],
                    identity_assurance="STRONG"
                    if request.participant_lookup_key
                    else "INSUFFICIENT",
                    presence_status=candidate["presence_status"],
                    patient_confirmation_status=snapshot["patient_confirmation_status"],
                    match_state=entry["match_state"],
                    score_facts_json={
                        "matched_items": sum(
                            row["match_result"] == "MATCHED"
                            for row in entry["item_results"]
                        ),
                        "patient_id": candidate["patient_id"],
                        "document_fingerprints": document_fingerprints,
                        "started_at": candidate.get("started_at"),
                        "ended_at": candidate.get("ended_at"),
                        "service_type": candidate.get("service_type"),
                    },
                    reasons_json=[
                        row["match_result"]
                        for row in entry["item_results"]
                        if row["match_result"] != "MATCHED"
                    ],
                )
            )
        await _finalize(
            session,
            request,
            run,
            selected,
            evaluated,
            match_status,
            claim_items,
            snapshot_digest,
            dependency_fingerprint,
        )


async def _finalize(
    session,
    request,
    run,
    selected,
    evaluated,
    match_status,
    claim_items,
    snapshot_digest,
    dependency_fingerprint,
) -> None:
    now = datetime.now(UTC)
    selected_id = UUID(selected["candidate"]["encounter_id"]) if selected else None
    for encounter_id in sorted(
        {UUID(entry["candidate"]["encounter_id"]) for entry in evaluated}, key=str
    ):
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": str(encounter_id)},
        )
    prior_claim = await session.scalar(
        select(VerificationRun)
        .join(VerificationRequest, VerificationRequest.id == VerificationRun.request_id)
        .where(
            VerificationRequest.claim_source == request.claim_source,
            VerificationRequest.claim_id == request.claim_id,
            VerificationRun.id != run.id,
            VerificationRun.status == "COMPLETED",
        )
        .order_by(VerificationRun.ended_at.desc())
    )
    conflicting: list[str] = []
    reused_evidence: list[str] = []
    active_associations = []
    if selected_id:
        active_associations = list(
            (
                await session.scalars(
                    select(ClaimEncounterAssociation).where(
                        ClaimEncounterAssociation.encounter_id == selected_id,
                        ClaimEncounterAssociation.status == "MATCHED",
                    )
                )
            ).all()
        )
        conflicting = sorted(
            {
                f"{row.claim_source}:{row.claim_id}"
                for row in active_associations
                if (row.claim_source, row.claim_id)
                != (request.claim_source, request.claim_id)
            }
        )
    item_results = selected["item_results"] if selected else []
    evidence_refs = [
        str(allocation["evidence_version_ref"])
        for item in item_results
        for allocation in item["allocations"]
    ]
    if evidence_refs:
        reused_evidence = [
            str(value)
            for value in (
                await session.scalars(
                    select(ClaimEvidenceAssociation.evidence_version_ref)
                    .join(
                        ClaimEncounterAssociation,
                        ClaimEncounterAssociation.id
                        == ClaimEvidenceAssociation.association_id,
                    )
                    .where(
                        ClaimEvidenceAssociation.evidence_version_ref.in_(
                            [UUID(value) for value in evidence_refs]
                        ),
                        ClaimEvidenceAssociation.status == "ACTIVE",
                        ClaimEncounterAssociation.status == "MATCHED",
                        ClaimEvidenceAssociation.claim_id != request.claim_id,
                    )
                )
            ).all()
        ]
    identity = "STRONG" if request.participant_lookup_key else "INSUFFICIENT"
    confirmation = (
        selected["snapshot"]["patient_confirmation_status"]
        if selected
        else "NOT_APPLICABLE"
    )
    presence = selected["candidate"]["presence_status"] if selected else "UNKNOWN"
    time_inconsistent = (
        _time_issue(request, selected["snapshot"]["items"]) if selected else None
    )
    cross_patient = (
        await _cross_patient_fingerprints(session, selected, run.id) if selected else []
    )
    facts = {
        "encounter_match_status": match_status,
        "identity_assurance": identity,
        "item_results": item_results,
        "time_inconsistent": time_inconsistent,
        "encounter_reused": bool(conflicting),
        "conflicting_claims": conflicting,
        "evidence_reused": bool(reused_evidence),
        "reused_evidence_refs": reused_evidence,
        "claim_reverified": bool(prior_claim),
        "prior_run_id": str(prior_claim.id) if prior_claim else None,
        "data_freshness": "CURRENT",
        "late_evidence": False,
        "document_cross_patient": bool(cross_patient),
        "cross_patient_fingerprints": cross_patient,
        "presence_status": presence,
        "patient_confirmation_status": confirmation,
    }
    findings = evaluate_rules(facts)
    for result in item_results:
        session.add(
            ItemEvaluation(
                id=uuid4(),
                run_id=run.id,
                encounter_id=selected_id,
                claim_item_ref=result["claim_item_ref"],
                evidence_version_ref=UUID(result["evidence_version_ref"])
                if result["evidence_version_ref"]
                else None,
                evidence_id=UUID(result["evidence_id"])
                if result["evidence_id"]
                else None,
                match_result=result["match_result"],
                claimed_quantity=result["claimed_quantity"],
                allocated_evidence_quantity=result["allocated_evidence_quantity"],
                reason=result["reason"],
            )
        )
    for finding in findings:
        session.add(
            RuleFinding(
                id=uuid4(),
                run_id=run.id,
                encounter_id=selected_id,
                evidence_refs_json=finding.pop("evidence_refs"),
                explanation_facts_json=finding.pop("explanation_facts"),
                limitations_text=finding.pop("limitations_text"),
                **finding,
            )
        )
    if selected_id:
        association = ClaimEncounterAssociation(
            id=uuid4(),
            claim_source=request.claim_source,
            claim_id=request.claim_id,
            claim_revision=request.claim_revision,
            encounter_id=selected_id,
            status="RETRACTED"
            if request.claim_relationship_type == "REVERSAL"
            else "MATCHED",
            effective_from_run=run.id,
        )
        session.add(association)
        if request.claim_relationship_type in {"CORRECTION", "REVERSAL"}:
            for old in active_associations:
                if old.claim_id == request.related_claim_id:
                    old.status, old.superseded_by = "SUPERSEDED", association.id
        for result in item_results:
            for allocation in result["allocations"]:
                session.add(
                    ClaimEvidenceAssociation(
                        id=uuid4(),
                        association_id=association.id,
                        claim_source=request.claim_source,
                        claim_id=request.claim_id,
                        claim_item_ref=result["claim_item_ref"],
                        evidence_ref=UUID(allocation["evidence_id"]),
                        evidence_version_ref=UUID(allocation["evidence_version_ref"]),
                        allocated_quantity=allocation["quantity"],
                        relationship="CONSUMED_PARTIAL"
                        if allocation["quantity"] < result["claimed_quantity"]
                        else "CONSUMED_FULL",
                        status="ACTIVE",
                    )
                )
    matched = sum(item["match_result"] == "MATCHED" for item in item_results)
    run.status, request.request_status = "COMPLETED", "COMPLETED"
    run.encounter_match_status, run.selected_encounter_id = match_status, selected_id
    run.candidate_count, run.evaluated_candidate_count = len(evaluated), len(evaluated)
    run.identity_assurance, run.evidence_reconciliation_status = (
        identity,
        "ITEMS_CONSISTENT"
        if item_results and matched == len(item_results)
        else "PARTIAL_MATCH"
        if matched
        else "EVIDENCE_INCOMPLETE",
    )
    run.matched_items_count, run.unmatched_items_count = (
        matched,
        len(item_results) - matched,
    )
    run.duplicate_assessment_status = (
        "POTENTIAL_EVIDENCE_REUSE"
        if reused_evidence
        else "POTENTIAL_ENCOUNTER_REUSE"
        if conflicting
        else "NO_REUSE_FOUND_IN_JEJAKJKN_HISTORY"
    )
    run.conflicting_claims_json, run.patient_confirmation_status = (
        conflicting,
        confirmation,
    )
    (
        run.review_required,
        run.input_snapshot_digest,
        run.dependency_fingerprint,
        run.ended_at,
    ) = (
        # INFO signals such as "patient has not answered" stay on record without a review case.
        match_status == "AMBIGUOUS_MATCH"
        or any(finding["severity"] != "INFO" for finding in findings),
        snapshot_digest,
        dependency_fingerprint,
        now,
    )
    event_type = (
        "verification.duplicate_suspected.v1"
        if conflicting or reused_evidence
        else "verification.completed.v1"
    )
    session.add(
        VerificationOutbox(
            event_id=uuid4(),
            event_type=event_type,
            aggregate_id=str(run.id),
            aggregate_revision=run.run_number,
            organization_id=str(request.verifier_org_id),
            correlation_id=str(request.id),
            causation_id=None,
            payload={
                "verification_id": str(request.id),
                "run_id": str(run.id),
                "selected_encounter_id": str(selected_id) if selected_id else None,
                "finding_count": len(findings),
            },
            occurred_at=now,
        )
    )
    await session.commit()


async def _cross_patient_fingerprints(session, selected, run_id) -> list[str]:
    # shortcut: no template-hash allowlist in the synthetic catalog, add one when real document templates are ingested.
    current = {
        item["code"]
        for item in selected["snapshot"]["items"]
        if item["kind"] == "DOCUMENT_FINGERPRINT"
        and item["status"] in {"ACTIVE", "CORRECTED"}
    }
    if not current:
        return []
    patient_id = selected["candidate"]["patient_id"]
    rows = (
        await session.scalars(
            select(CandidateEvaluation).where(CandidateEvaluation.run_id != run_id)
        )
    ).all()
    return sorted(
        current.intersection(
            {
                fingerprint
                for row in rows
                if row.score_facts_json.get("patient_id") != patient_id
                for fingerprint in row.score_facts_json.get("document_fingerprints", [])
            }
        )
    )


def _time_issue(request, evidence_items) -> str | None:
    for item in evidence_items:
        occurred = datetime.fromisoformat(item["occurred_at"])
        if (
            occurred < request.service_period_start
            or occurred > request.service_period_end
        ):
            return "Evidence timestamp falls outside the claimed service period"
    return None


def _item_dict(item) -> dict:
    return {
        "item_ref": item.item_ref,
        "item_type": item.item_type,
        "code_system": item.code_system,
        "code": item.code,
        "quantity": item.quantity,
        "unit": item.unit,
        "service_date_start": item.service_date_start,
        "service_date_end": item.service_date_end,
    }


def _digest(value: dict) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


async def run_forever() -> None:
    while True:
        try:
            processed = await process_one()
        except Exception:
            logger.exception("verification polling failed")
            await asyncio.sleep(2)
            continue
        if not processed:
            await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(run_forever())
