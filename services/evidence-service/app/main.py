"""Evidence service shell; domain endpoints arrive in Gate 2."""

from fastapi import FastAPI

app = FastAPI(title="JejakJKN Evidence Service", version="0.1.0")


@app.get("/health", tags=["operations"])
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "evidence-service", "gate": "planned-gate-2"}


@app.get("/ready", tags=["operations"])
async def ready() -> dict[str, str]:
    return {"status": "ready"}
