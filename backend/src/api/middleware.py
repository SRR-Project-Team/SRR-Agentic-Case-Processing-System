#!/usr/bin/env python3
"""Shared API middleware and exception setup."""

from __future__ import annotations

import traceback
from typing import Any, List

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

try:
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    from slowapi.middleware import SlowAPIMiddleware
    from slowapi.util import get_remote_address

    _SLOWAPI_AVAILABLE = True
except Exception:
    Limiter = Any  # type: ignore[assignment]
    _rate_limit_exceeded_handler = None
    RateLimitExceeded = Exception  # type: ignore[assignment]
    SlowAPIMiddleware = None
    _SLOWAPI_AVAILABLE = False

from config.settings import FEATURE_RATE_LIMIT, RATE_LIMIT_DEFAULT
try:
    from utils.metrics import MetricsMiddleware
    _METRICS_AVAILABLE = True
except Exception:
    MetricsMiddleware = None  # type: ignore[assignment]
    _METRICS_AVAILABLE = False


def _cors_headers_for(request: Request, allowed_origins: List[str]) -> dict:
    origin = request.headers.get("origin")
    if origin and origin in allowed_origins:
        return {
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Methods": "*",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Allow-Credentials": "true",
        }
    return {}


def register_exception_handlers(app: FastAPI, allowed_origins: List[str]) -> None:
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        error_detail = {
            "type": type(exc).__name__,
            "path": str(request.url),
            "method": request.method,
        }
        print(f"❌ Global exception caught: {error_detail}, detail={exc}")
        traceback.print_exc()
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"status": "error", "message": "Internal server error"},
            headers=_cors_headers_for(request, allowed_origins),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": exc.errors(), "body": exc.body},
            headers=_cors_headers_for(request, allowed_origins),
        )


def configure_rate_limit(app: FastAPI) -> Limiter | None:
    if not FEATURE_RATE_LIMIT:
        return None
    if not _SLOWAPI_AVAILABLE:
        print("⚠️ FEATURE_RATE_LIMIT is enabled but slowapi is not installed; rate limiting is disabled.")
        return None
    limiter = Limiter(key_func=get_remote_address, default_limits=[RATE_LIMIT_DEFAULT])
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)
    return limiter


def configure_metrics(app: FastAPI) -> None:
    if not _METRICS_AVAILABLE:
        print("⚠️ prometheus_client is not installed; metrics middleware is disabled.")
        return
    app.add_middleware(MetricsMiddleware)
