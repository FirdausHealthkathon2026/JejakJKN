"""Review service shell; domain endpoints arrive in Gate 6."""

from fastapi import FastAPI

app = FastAPI(title="JejakJKN Review Service", version="0.1.0")


@app.get("/health", tags=["operations"])
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "review-service", "gate": "planned-gate-6"}


@app.get("/ready", tags=["operations"])
async def ready() -> dict[str, str]:
    return {"status": "ready"}
