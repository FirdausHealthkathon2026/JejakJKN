"""Gate 1 SIMRS scanner relay; clinical recording starts in Gate 2."""

import os
from uuid import UUID

import httpx
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api")


class ScanRequest(BaseModel):
    qr_token: str = Field(min_length=32)
    scanner_external_id: str = Field(default="SIMRS-A-SCANNER-01", min_length=1, max_length=128)
    external_visit_reference: str | None = Field(default=None, max_length=128)


async def _access_token(client: httpx.AsyncClient) -> str:
    response = await client.post(
        os.environ["KEYCLOAK_TOKEN_URL"],
        data={
            "grant_type": "client_credentials",
            "client_id": os.environ["SIMRS_CLIENT_ID"],
            "client_secret": os.environ["SIMRS_CLIENT_SECRET"],
        },
    )
    response.raise_for_status()
    return response.json()["access_token"]


async def _scan(kind: str, body: ScanRequest, idempotency_key: UUID) -> tuple[dict, int]:
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            token = await _access_token(client)
            payload = body.model_dump()
            payload["facility_external_code"] = os.environ["FACILITY_EXTERNAL_CODE"]
            if kind == "check-out":
                payload.pop("external_visit_reference", None)
            response = await client.post(
                f"{os.environ['JEJAKJKN_API_URL']}/api/v1/integrations/qr/{kind}",
                json=payload,
                headers={"Authorization": f"Bearer {token}", "Idempotency-Key": str(idempotency_key)},
            )
        except httpx.HTTPError as exc:
            raise HTTPException(503, "JejakJKN or identity provider is unavailable") from exc
    if response.is_error:
        raise HTTPException(response.status_code, response.json())
    return response.json(), response.status_code


@router.post("/scan/check-in")
async def check_in(body: ScanRequest, idempotency_key: UUID = Header(alias="Idempotency-Key")) -> dict:
    result, _ = await _scan("check-in", body, idempotency_key)
    return result


@router.post("/scan/check-out")
async def check_out(body: ScanRequest, idempotency_key: UUID = Header(alias="Idempotency-Key")) -> dict:
    result, _ = await _scan("check-out", body, idempotency_key)
    return result
