#!/usr/bin/env python3
"""System/operational routes."""

from __future__ import annotations

from fastapi import APIRouter

from config.settings import FEATURE_METRICS
from utils.metrics import metrics_response


def build_system_router() -> APIRouter:
    router = APIRouter(tags=["system"])

    @router.get("/metrics")
    async def metrics():
        if not FEATURE_METRICS:
            return {"status": "disabled"}
        return metrics_response()

    @router.get("/health")
    async def health_check():
        return {
            "status": "healthy",
            "message": "SRR case processing API is running normally, supports TXT and PDF files",
        }

    return router
