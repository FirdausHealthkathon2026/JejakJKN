"""RFC 9457-compatible application errors shared by APIs."""

from dataclasses import dataclass
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


@dataclass(slots=True)
class Problem(Exception):
    status: int
    code: str
    title: str
    detail: str
    headers: dict[str, str] | None = None


async def problem_handler(request: Request, exc: Problem) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "unknown")
    body: dict[str, Any] = {
        "type": f"https://jejakjkn.local/problems/{exc.code.lower().replace('_', '-')}",
        "title": exc.title,
        "status": exc.status,
        "detail": exc.detail,
        "instance": request.url.path,
        "error_code": exc.code,
        "request_id": request_id,
        "correlation_id": request.headers.get("X-Correlation-Id", request_id),
    }
    return JSONResponse(body, status_code=exc.status, media_type="application/problem+json", headers=exc.headers)
