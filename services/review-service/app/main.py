"""Human review and tamper-evident audit API."""

from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from jejakjkn_canonical.problems import Problem, problem_handler
from jejakjkn_observability import install_observability

from app.api.routes_internal import router as internal_router
from app.api.routes_public import router
from app.infrastructure.db import database_ready

app = FastAPI(title="JejakJKN Review Service", version="1.0.0")
install_observability(app, "review-service")
app.add_exception_handler(Problem, problem_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5175"],
    allow_methods=["GET", "POST"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "Idempotency-Key",
        "X-Request-Id",
        "X-Access-Purpose",
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
    return {"status": "ok", "service": "review-service", "gate": "implemented-gate-6"}


@app.get("/ready", tags=["operations"])
async def ready() -> dict[str, str]:
    if not await database_ready():
        raise Problem(
            503, "DEPENDENCY_UNAVAILABLE", "Not ready", "PostgreSQL is unavailable."
        )
    return {"status": "ready"}
