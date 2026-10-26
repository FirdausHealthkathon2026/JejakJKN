"""SIMRS-B alternative-schema adapter demo."""

from fastapi import FastAPI

from app.api.routes import router

app = FastAPI(title="SIMRS B Alternative Adapter", version="1.0.0")
app.include_router(router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "simrs-b-backend",
        "scope": "gate-7-alternative-adapter",
    }


@app.get("/ready")
async def ready() -> dict[str, str]:
    return {"status": "ready"}
