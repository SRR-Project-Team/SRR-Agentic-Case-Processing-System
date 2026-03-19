#!/usr/bin/env python3
"""Unified slope/tree enrichment service used by extractors."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

import pytz
from database import get_db_manager
from database.models import Slope
from services.external_data_service import ExternalDataService
from services.tree_id_resolver import TreeIDResolver
from utils.slope_location_mapper import clean_slope_number, get_location_from_slope_no


class SlopeService:
    """Unify slope id normalization and tree id extraction."""

    def __init__(self) -> None:
        self.tree_resolver = TreeIDResolver()
        self.external = ExternalDataService()
        self.db_manager = get_db_manager()

    def enrich_case_data(self, case_data: Dict[str, Any]) -> Dict[str, Any]:
        result = dict(case_data or {})

        slope_no = (result.get("G_slope_no") or "").strip()
        if slope_no:
            normalized_slope = clean_slope_number(slope_no)
            if normalized_slope:
                result["G_slope_no"] = normalized_slope
                if not result.get("H_location"):
                    result["H_location"] = get_location_from_slope_no(normalized_slope)

        if not result.get("tree_id"):
            full_tree_id = self.tree_resolver.resolve_from_case(result)
            if full_tree_id:
                result["tree_id"] = full_tree_id
                parts = full_tree_id.split()
                if len(parts) >= 2:
                    result["tree_no"] = parts[-1]

        return result

    def _infer_department_from_text(self, text: str) -> str:
        raw = (text or "").strip()
        lowered = raw.lower()
        if not raw:
            return "unknown"
        # Keep conservative mapping; preserve original for unknown tokens.
        if "architectural services" in lowered or lowered in {"asd", "archsd"}:
            return "ASD"
        if "highways" in lowered or lowered == "hyd":
            return "HyD"
        if "civil engineering" in lowered or lowered in {"cedd", "geo"}:
            return "CEDD"
        if "drainage" in lowered or lowered == "dsd":
            return "DSD"
        if "private" in lowered:
            return "Private"
        return raw

    def _load_local_responsibility(self, slope_no: str) -> Dict[str, Any]:
        """Load slope responsibility from local DB cache."""
        session = self.db_manager.get_session()
        try:
            row = (
                session.query(Slope)
                .filter(Slope.slope_no == slope_no)
                .first()
            )
            if not row:
                return {"department": "unknown", "confidence": "low", "source": "unknown", "raw_data": {}}
            dept = self._infer_department_from_text(getattr(row, "maintenance_responsible", "") or "")
            if dept == "unknown":
                return {"department": "unknown", "confidence": "low", "source": "local_db", "raw_data": {}}
            return {
                "department": dept,
                "confidence": "medium",
                "source": "local_db",
                "raw_data": {
                    "maintenance_responsible": getattr(row, "maintenance_responsible", None),
                    "maintenance_source": getattr(row, "maintenance_source", None),
                    "last_verified_at": str(getattr(row, "last_verified_at", None) or ""),
                },
            }
        finally:
            session.close()

    async def determine_department(self, slope_no: str) -> Dict[str, Any]:
        """Determine responsible department for a slope."""
        normalized_slope = clean_slope_number(slope_no or "") or (slope_no or "").strip()
        if not normalized_slope:
            return {"department": "unknown", "confidence": "low", "source": "unknown", "raw_data": {}}

        api_data = await self.external.query_slope_responsibility(normalized_slope)
        if api_data:
            dept = self._infer_department_from_text(api_data.get("maintenance_responsible", ""))
            if dept != "unknown":
                # Best effort local cache write-through for fallback usage.
                session = self.db_manager.get_session()
                try:
                    row = session.query(Slope).filter(Slope.slope_no == normalized_slope).first()
                    if row:
                        row.maintenance_responsible = api_data.get("maintenance_responsible", "") or None
                        row.maintenance_source = "api"
                        row.last_verified_at = datetime.now(pytz.timezone("Asia/Shanghai"))
                        session.commit()
                except Exception:
                    session.rollback()
                finally:
                    session.close()
                return {"department": dept, "confidence": "high", "source": "api", "raw_data": api_data}

        return self._load_local_responsibility(normalized_slope)

    async def check_multi_department(self, slope_nos: List[str]) -> Dict[str, Any]:
        """Check whether multiple slopes map to multiple departments."""
        cleaned: List[str] = []
        seen = set()
        for slope in slope_nos or []:
            normalized = clean_slope_number(slope or "") or (slope or "").strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                cleaned.append(normalized)

        departments: Dict[str, str] = {}
        for slope in cleaned:
            result = await self.determine_department(slope)
            departments[slope] = result.get("department", "unknown")

        distinct_departments = {v for v in departments.values() if v and v != "unknown"}
        split_needed = len(distinct_departments) > 1
        recommendation = (
            "Split into sub-tasks by department."
            if split_needed
            else "Single department handling is sufficient."
        )
        return {
            "split_needed": split_needed,
            "departments": departments,
            "recommendation": recommendation,
        }
