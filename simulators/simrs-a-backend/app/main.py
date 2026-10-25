"""SIMRS-A scanner, clinical source, and durable adapter."""

import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.infrastructure.db import database_ready
from app.infrastructure.sync_dispatcher import dispatch_forever


@asynccontextmanager
async def lifespan(_: FastAPI):
    task = asyncio.create_task(dispatch_forever())
    yield
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


app = FastAPI(title="SIMRS A Gate 2 Clinical Simulator", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5174"], allow_methods=["*"], allow_headers=["*"])
app.include_router(router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "simrs-a-backend", "scope": "gate-2-clinical-source"}


@app.get("/ready")
async def ready() -> dict[str, str]:
    return {"status": "ready" if await database_ready() else "not-ready"}
