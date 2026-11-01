"""Evidence, checkout summary, and patient confirmation API."""

import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from jejakjkn_canonical.problems import Problem, problem_handler
from jejakjkn_observability import install_observability

from app.api.routes_internal import router as internal_router
from app.api.routes_public import router
from app.application.use_cases import EvidenceApplication
from app.config import get_settings
from app.infrastructure.db import SessionFactory, database_ready

logger = logging.getLogger(__name__)


async def no_response_worker() -> None:
    while True:
        try:
            async with SessionFactory() as session:
                await EvidenceApplication(
                    session, get_settings()
                ).mark_expired_no_responses(datetime.now(UTC))
        except Exception:
            logger.exception("NO_RESPONSE worker failed")
        await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(_: FastAPI):
    task = asyncio.create_task(no_response_worker())
    yield
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


app = FastAPI(
    title="JejakJKN Evidence & Confirmation Service", version="1.0.0", lifespan=lifespan
)
install_observability(app, "evidence-service")
app.add_exception_handler(Problem, problem_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "Idempotency-Key",
        "X-Request-Id",
        "X-Correlation-Id",
    ],
)
app.include_router(router)
app.include_router(internal_router)


@app.exception_handler(RequestValidationError)
async def validation_problem(request: Request, exc: RequestValidationError):
    return await problem_handler(
        request,
        Problem(
            422,
            "VALIDATION_ERROR",
            "Request validation failed",
            "; ".join(error["msg"] for error in exc.errors()),
        ),
    )


@app.middleware("http")
async def request_context(request: Request, call_next):
    request.state.request_id = request.headers.get("X-Request-Id", str(uuid4()))
    response = await call_next(request)
    response.headers["X-Request-Id"] = request.state.request_id
    return response


@app.get("/health", tags=["operations"])
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "evidence-service",
        "gate": "implemented-gate-2-4",
    }


@app.get("/ready", tags=["operations"])
async def ready() -> dict[str, str]:
    if not await database_ready():
        raise Problem(
            503, "DEPENDENCY_UNAVAILABLE", "Not ready", "PostgreSQL is unavailable."
        )
    return {"status": "ready"}
