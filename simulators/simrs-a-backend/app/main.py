"""SIMRS A scanner simulator entrypoint."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router

app = FastAPI(title="SIMRS A Gate 1 Scanner", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5174"], allow_methods=["*"], allow_headers=["*"])
app.include_router(router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "simrs-a-backend", "scope": "gate-1-scanner-only"}
