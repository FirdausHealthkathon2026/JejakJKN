"""BPJS claim system simulator: facilities submit here, and verifiers read claims from here."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from jejakjkn_observability import install_observability
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import DateTime, Numeric, String, Text, func, select
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

STATUS_FIELDS = {"VERIFYING": "verifying_at", "DONE": "done_at"}
FACILITIES = {
    "HOSP-DEMO-001": ("10001", "RS Demo Satu"),
    "HOSP-DEMO-002": ("10002", "RS Demo Dua"),
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")
    bpjs_claim_database_url: str


settings = Settings()
engine = create_async_engine(settings.bpjs_claim_database_url, pool_pre_ping=True)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Claim(Base):
    __tablename__ = "claims"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    source: Mapped[str] = mapped_column(String(16), index=True)
    file_name: Mapped[str | None] = mapped_column(String(255))
    revision: Mapped[str] = mapped_column(String(64), default="1")
    relationship: Mapped[str] = mapped_column(String(16), default="ORIGINAL")
    related_claim_id: Mapped[str | None] = mapped_column(String(128))
    participant_number: Mapped[str | None] = mapped_column(String(64))
    patient_name: Mapped[str | None] = mapped_column(String(255))
    facility_code: Mapped[str] = mapped_column(String(64), index=True)
    facility_name: Mapped[str] = mapped_column(String(255))
    visit_reference: Mapped[str | None] = mapped_column(String(128))
    encounter_id: Mapped[str | None] = mapped_column(String(64))
    service_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    service_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    care_type: Mapped[str] = mapped_column(String(2), default="RJ")
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    status: Mapped[str] = mapped_column(String(16), default="RECEIVED")
    items: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    note: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    verifying_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ClaimItem(BaseModel):
    item_ref: str = Field(min_length=1, max_length=64)
    item_type: Literal["DIAGNOSIS", "PROCEDURE", "MEDICATION", "MEDICATION_DISPENSE"]
    code_system: str = Field(min_length=1, max_length=64)
    code: str = Field(min_length=1, max_length=64)
    display: str = Field(min_length=1, max_length=255)
    quantity: Decimal = Field(default=Decimal("1"), gt=0)
    unit: str = Field(default="1", min_length=1, max_length=32)
    local_code: str | None = None
    local_quantity: Decimal | None = None


class ClaimInput(BaseModel):
    id: str | None = Field(default=None, max_length=128)
    revision: str = "1"
    relationship: Literal["ORIGINAL", "CORRECTION", "REVERSAL"] = "ORIGINAL"
    related_claim_id: str | None = None
    participant_number: str | None = Field(default=None, min_length=3, max_length=64)
    patient_name: str | None = Field(default=None, min_length=2, max_length=255)
    facility_code: str
    visit_reference: str | None = None
    encounter_id: str | None = None
    service_start: datetime
    service_end: datetime
    care_type: Literal["RJ", "RI"] = "RJ"
    amount: Decimal = Field(gt=0)
    items: list[ClaimItem] = Field(min_length=1, max_length=500)


class ImportRequest(BaseModel):
    file_name: str = Field(min_length=1, max_length=255)
    claims: list[ClaimInput] = Field(min_length=1, max_length=5000)


class StatusRequest(BaseModel):
    status: Literal["VERIFYING", "DONE"]


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionFactory() as session:
        yield session


@asynccontextmanager
async def lifespan(_: FastAPI):
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(title="BPJS Claim System Simulator", version="1.0.0", lifespan=lifespan)
install_observability(app, "bpjs-claim-backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5174",
        "http://localhost:5175",
        "http://localhost:5176",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _view(row: Claim) -> dict:
    return {
        "id": row.id,
        "source": row.source,
        "file_name": row.file_name,
        "revision": row.revision,
        "relationship": row.relationship,
        "related_claim_id": row.related_claim_id,
        "participant_number": row.participant_number,
        "patient_name": row.patient_name,
        "facility_code": row.facility_code,
        "facility_name": row.facility_name,
        "visit_reference": row.visit_reference,
        "encounter_id": row.encounter_id,
        "service_start": row.service_start,
        "service_end": row.service_end,
        "care_type": row.care_type,
        "amount": float(row.amount),
        "status": row.status,
        "items": row.items,
        "submitted_at": row.submitted_at,
        "verifying_at": row.verifying_at,
        "done_at": row.done_at,
    }


def _values(body: ClaimInput, source: str, file_name: str | None = None) -> dict:
    if body.facility_code not in FACILITIES:
        raise HTTPException(422, "Kode faskes tidak dikenali.")
    return body.model_dump(mode="json", exclude={"items"}) | {
        "service_start": body.service_start,
        "service_end": body.service_end,
        "amount": body.amount,
        "source": source,
        "file_name": file_name,
        "facility_name": FACILITIES[body.facility_code][1],
        "items": [item.model_dump(mode="json") for item in body.items],
    }


async def _next_number(session: AsyncSession, facility_code: str) -> str:
    prefix = FACILITIES[facility_code][0] + datetime.now(UTC).strftime("%m%y") + "V"
    count = await session.scalar(
        select(func.count()).select_from(Claim).where(Claim.id.like(f"{prefix}%"))
    )
    return f"{prefix}{int(count or 0) + 1:06d}"


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "bpjs-claim-backend"}


@app.post("/api/claims", status_code=201)
async def submit_claim(
    body: ClaimInput, session: AsyncSession = Depends(get_session)
) -> dict:
    values = _values(body, "FASKES")
    values["id"] = body.id or await _next_number(session, body.facility_code)
    row = Claim(**values)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return _view(row)


@app.post("/api/claims/import", status_code=201)
async def import_claims(
    body: ImportRequest, session: AsyncSession = Depends(get_session)
) -> dict:
    rows = [_values(claim, "CSV", body.file_name) for claim in body.claims]
    for start in range(0, len(rows), 500):
        statement = insert(Claim).values(rows[start : start + 500])
        await session.execute(
            statement.on_conflict_do_update(
                index_elements=[Claim.id],
                set_={"amount": statement.excluded.amount, "items": statement.excluded["items"]},
            )
        )
    await session.commit()
    return {"imported": len(rows)}


@app.get("/api/claims")
async def list_claims(
    facility_code: str | None = None,
    limit: int = 2000,
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    query = select(Claim).order_by(Claim.submitted_at.desc(), Claim.id).limit(limit)
    if facility_code:
        query = query.where(Claim.facility_code == facility_code)
    return [_view(row) for row in (await session.scalars(query)).all()]


@app.get("/api/claims/{claim_id}")
async def get_claim(
    claim_id: str, session: AsyncSession = Depends(get_session)
) -> dict:
    row = await session.get(Claim, claim_id)
    if not row:
        raise HTTPException(404, "Klaim tidak ditemukan.")
    return _view(row)


@app.post("/api/claims/{claim_id}/status")
async def set_status(
    claim_id: str, body: StatusRequest, session: AsyncSession = Depends(get_session)
) -> dict:
    row = await session.get(Claim, claim_id, with_for_update=True)
    if not row:
        raise HTTPException(404, "Klaim tidak ditemukan.")
    row.status = body.status
    setattr(row, STATUS_FIELDS[body.status], datetime.now(UTC))
    await session.commit()
    return _view(row)
