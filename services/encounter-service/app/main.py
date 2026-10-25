"""Encounter & QR API."""

from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis

from jejakjkn_canonical.problems import Problem, problem_handler

from app.api.routes_internal import router as internal_router
from app.api.routes_public import router as public_router
from app.config import get_settings
from app.infrastructure.crypto import QrSigner
from app.infrastructure.db import database_ready
from app.infrastructure.redis_qr import RedisQrStore


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url, decode_responses=False)
    app.state.qr_store = RedisQrStore(redis)
    app.state.qr_signer = QrSigner(
        settings.qr_signing_private_key_path,
        settings.qr_signing_public_key_path,
        settings.qr_signing_kid,
        settings.qr_token_ttl_seconds,
    )
    yield
    await redis.aclose()


app = FastAPI(title="JejakJKN Encounter & QR Service", version="1.0.0", lifespan=lifespan)
app.add_exception_handler(Problem, problem_handler)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["GET", "POST"], allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-Id", "X-Correlation-Id"])
app.include_router(public_router)
app.include_router(internal_router)


@app.exception_handler(RequestValidationError)
async def validation_problem(request: Request, exc: RequestValidationError):
    problem = Problem(422, "VALIDATION_ERROR", "Request validation failed", "; ".join(error["msg"] for error in exc.errors()))
    return await problem_handler(request, problem)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request.state.request_id = request.headers.get("X-Request-Id", str(uuid4()))
    response = await call_next(request)
    response.headers["X-Request-Id"] = request.state.request_id
    return response


@app.get("/health", tags=["operations"])
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "encounter-service"}


@app.get("/ready", tags=["operations"])
async def ready(request: Request) -> dict[str, str]:
    if not await database_ready() or not await request.app.state.qr_store.ping():
        raise Problem(503, "DEPENDENCY_UNAVAILABLE", "Not ready", "PostgreSQL or Redis is unavailable.")
    return {"status": "ready"}
