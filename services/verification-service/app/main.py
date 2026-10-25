"""Verification service shell; domain endpoints arrive in Gate 4."""

from fastapi import FastAPI

app = FastAPI(title="JejakJKN Verification Service", version="0.1.0")


@app.get("/health", tags=["operations"])
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "verification-service", "gate": "planned-gate-4"}


@app.get("/ready", tags=["operations"])
async def ready() -> dict[str, str]:
    return {"status": "ready"}
