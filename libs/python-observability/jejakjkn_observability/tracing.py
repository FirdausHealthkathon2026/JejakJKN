"""Dependency-free W3C trace propagation and Prometheus request metrics."""

import asyncio
import base64
import json
import logging
import os
import re
import time
from collections import defaultdict
from secrets import token_hex

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
import httpx

TRACEPARENT = re.compile(r"^00-([0-9a-f]{32})-([0-9a-f]{16})-0[01]$")


def install_observability(app: FastAPI, service: str) -> None:
    counts: dict[tuple[str, str, int], int] = defaultdict(int)
    durations: dict[tuple[str, str], float] = defaultdict(float)
    logger = logging.getLogger("jejakjkn.http")
    spans: asyncio.Queue[dict] = asyncio.Queue(maxsize=1000)
    sender: asyncio.Task | None = None

    async def export_spans() -> None:
        endpoint = os.getenv(
            "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "http://otel-collector:4318/v1/traces"
        )
        async with httpx.AsyncClient(timeout=1) as client:
            while True:
                span = await spans.get()
                try:
                    await client.post(
                        endpoint,
                        json={
                            "resourceSpans": [
                                {
                                    "resource": {
                                        "attributes": [
                                            {
                                                "key": "service.name",
                                                "value": {"stringValue": service},
                                            }
                                        ]
                                    },
                                    "scopeSpans": [
                                        {
                                            "scope": {"name": "jejakjkn-observability"},
                                            "spans": [span],
                                        }
                                    ],
                                }
                            ]
                        },
                    )
                except httpx.HTTPError:
                    pass
                finally:
                    spans.task_done()

    @app.middleware("http")
    async def observe(request: Request, call_next):
        nonlocal sender
        if sender is None or sender.done():
            sender = asyncio.create_task(export_spans())
        started = time.perf_counter()
        started_ns = time.time_ns()
        incoming = TRACEPARENT.match(request.headers.get("traceparent", ""))
        trace_id, span_id = (
            (incoming.group(1), incoming.group(2))
            if incoming
            else (token_hex(16), token_hex(8))
        )
        request.state.trace_id = trace_id
        response = await call_next(request)
        route = getattr(request.scope.get("route"), "path", request.url.path)
        elapsed = time.perf_counter() - started
        counts[(request.method, route, response.status_code)] += 1
        durations[(request.method, route)] += elapsed
        response.headers["traceparent"] = f"00-{trace_id}-{span_id}-01"
        response.headers["X-Trace-Id"] = trace_id
        logger.info(
            json.dumps(
                {
                    "service": service,
                    "trace_id": trace_id,
                    "request_id": getattr(request.state, "request_id", None),
                    "method": request.method,
                    "route": route,
                    "status": response.status_code,
                    "duration_ms": round(elapsed * 1000, 2),
                },
                separators=(",", ":"),
            )
        )
        span = {
            "traceId": base64.b64encode(bytes.fromhex(trace_id)).decode(),
            "spanId": base64.b64encode(bytes.fromhex(span_id)).decode(),
            "name": f"{request.method} {route}",
            "kind": 2,
            "startTimeUnixNano": str(started_ns),
            "endTimeUnixNano": str(started_ns + int(elapsed * 1_000_000_000)),
            "attributes": [
                {
                    "key": "http.request.method",
                    "value": {"stringValue": request.method},
                },
                {"key": "http.route", "value": {"stringValue": route}},
                {
                    "key": "http.response.status_code",
                    "value": {"intValue": str(response.status_code)},
                },
            ],
            "status": {"code": 2 if response.status_code >= 500 else 1},
        }
        try:
            spans.put_nowait(span)
        except asyncio.QueueFull:
            pass
        return response

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> PlainTextResponse:
        lines = [
            "# HELP http_requests_total Completed HTTP requests.",
            "# TYPE http_requests_total counter",
        ]
        for (method, route, status), value in sorted(counts.items()):
            labels = f'method="{method}",route="{route}",status="{status}",service="{service}"'
            lines.append(f"http_requests_total{{{labels}}} {value}")
        lines.extend(
            [
                "# HELP http_request_duration_seconds_sum Total request duration.",
                "# TYPE http_request_duration_seconds_sum counter",
            ]
        )
        for (method, route), value in sorted(durations.items()):
            labels = f'method="{method}",route="{route}",service="{service}"'
            lines.append(f"http_request_duration_seconds_sum{{{labels}}} {value:.6f}")
        return PlainTextResponse(
            "\n".join(lines) + "\n", media_type="text/plain; version=0.0.4"
        )
