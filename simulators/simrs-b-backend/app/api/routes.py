"""Lean second-vendor adapter path with a deliberately different local schema."""

import os
from uuid import UUID

import httpx
from fastapi import APIRouter, Header, HTTPException

from app.domain.models import LocalClinicalInput, LocalScanInput
from simrs_b_adapter.translator import translate

router = APIRouter(prefix="/api")


async def token(client: httpx.AsyncClient) -> str:
    response = await client.post(
        os.getenv(
            "KEYCLOAK_TOKEN_URL",
            "http://keycloak:8080/realms/jejakjkn-dev/protocol/openid-connect/token",
        ),
        data={
            "grant_type": "client_credentials",
            "client_id": "simrs-b-adapter",
            "client_secret": os.getenv("SIMRS_CLIENT_SECRET", "change-me-local-only"),
        },
    )
    response.raise_for_status()
    return response.json()["access_token"]


@router.post("/pindai/masuk")
async def check_in(
    body: LocalScanInput, idempotency_key: UUID = Header(alias="Idempotency-Key")
) -> dict:
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            access_token = await token(client)
            response = await client.post(
                f"{os.getenv('JEJAKJKN_API_URL', 'http://api-gateway:8080')}/api/v1/integrations/qr/check-in",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Idempotency-Key": str(idempotency_key),
                },
                json={
                    "qr_token": body.token_qr,
                    "scanner_external_id": body.id_pemindai,
                    "facility_external_code": "HOSP-DEMO-002",
                    "external_visit_reference": body.referensi_kunjungan,
                },
            )
        except httpx.HTTPError as exc:
            raise HTTPException(
                503, "JejakJKN or identity provider is unavailable"
            ) from exc
    if response.is_error:
        raise HTTPException(response.status_code, response.json())
    return response.json()


@router.post("/kunjungan/{encounter_id}/catatan", status_code=201)
async def create_record(
    encounter_id: UUID,
    body: LocalClinicalInput,
    idempotency_key: UUID = Header(alias="Idempotency-Key"),
) -> dict:
    payload = translate(body.model_dump())
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            access_token = await token(client)
            response = await client.post(
                f"{os.getenv('JEJAKJKN_API_URL', 'http://api-gateway:8080')}/api/v1/integrations/encounters/{encounter_id}/events",
                json=payload,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Idempotency-Key": str(idempotency_key),
                },
            )
        except httpx.HTTPError as exc:
            raise HTTPException(
                503, "JejakJKN or identity provider is unavailable"
            ) from exc
    if response.is_error:
        raise HTTPException(response.status_code, response.json())
    return {"canonical_payload": payload, "delivery": response.json()}
