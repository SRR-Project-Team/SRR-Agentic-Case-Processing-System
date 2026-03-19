#!/usr/bin/env python3
"""Prometheus metrics helpers."""

from __future__ import annotations

import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

try:
    from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

    _PROMETHEUS_AVAILABLE = True
except Exception:
    CONTENT_TYPE_LATEST = "text/plain; charset=utf-8"
    _PROMETHEUS_AVAILABLE = False

    class _NoopMetric:
        def labels(self, **_kwargs):
            return self

        def inc(self, *_args, **_kwargs):
            return None

        def dec(self, *_args, **_kwargs):
            return None

        def observe(self, *_args, **_kwargs):
            return None

    def Counter(*_args, **_kwargs):  # type: ignore[override]
        return _NoopMetric()

    def Gauge(*_args, **_kwargs):  # type: ignore[override]
        return _NoopMetric()

    def Histogram(*_args, **_kwargs):  # type: ignore[override]
        return _NoopMetric()

    def generate_latest() -> bytes:  # type: ignore[override]
        return b"# prometheus_client is not installed\n"


REQUEST_COUNT = Counter(
    "srr_http_requests_total",
    "HTTP requests count",
    ["method", "path", "status_code"],
)
REQUEST_LATENCY = Histogram(
    "srr_http_request_duration_seconds",
    "HTTP request latency",
    ["method", "path"],
)
ACTIVE_REQUESTS = Gauge("srr_http_requests_in_flight", "In-flight HTTP requests")


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable):
        path = request.url.path
        method = request.method
        ACTIVE_REQUESTS.inc()
        start = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            elapsed = time.perf_counter() - start
            REQUEST_LATENCY.labels(method=method, path=path).observe(elapsed)
            REQUEST_COUNT.labels(method=method, path=path, status_code=str(status_code)).inc()
            ACTIVE_REQUESTS.dec()


def metrics_response() -> Response:
    if not _PROMETHEUS_AVAILABLE:
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST, status_code=503)
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
