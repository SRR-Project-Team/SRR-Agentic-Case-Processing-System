from __future__ import annotations

import re
from typing import Any, Dict, List

from agent.abilities.base import register_ability
from agent.task_state import TaskState
from services.external_data_service import ExternalDataService


class _PassThroughAbility:
    required_fields: List[str] = []

    async def execute(self, state: TaskState) -> TaskState:
        return state


@register_ability
class CallExternalAbility(_PassThroughAbility):
    name = "call_external"

    _SLOPE_PATTERN = re.compile(
        r"\b(?:\d{1,2}[A-Z]{2,3}-[A-Z0-9/()\-]+|SA\d+)\b",
        re.IGNORECASE,
    )

    def __init__(self) -> None:
        self._service = ExternalDataService()

    def _extract_slope_candidates(self, state: TaskState) -> List[str]:
        values: List[str] = []
        for key in ("G_slope_no", "H_location", "Q_case_details", "I_nature_of_request"):
            raw = str((state.fields or {}).get(key) or "").strip()
            if raw:
                values.append(raw)

        unique: List[str] = []
        seen = set()
        for value in values:
            for match in self._SLOPE_PATTERN.findall(value):
                slope = match.strip().upper()
                if slope and slope not in seen:
                    seen.add(slope)
                    unique.append(slope)
        return unique

    async def execute(self, state: TaskState) -> TaskState:
        try:
            slope_candidates = self._extract_slope_candidates(state)
            primary_slope = slope_candidates[0] if slope_candidates else ""
            payload = await self._service.query_all(primary_slope or None)
            merged: Dict[str, Any] = dict(state.external_data or {})
            merged["external_sources"] = payload
            merged["smris"] = payload.get("smris")
            merged["cedd"] = payload.get("cedd")
            weather_data = payload.get("weather") or []
            merged["weather"] = weather_data
            merged["weather_hint"] = weather_data
            if slope_candidates:
                merged["slope_candidates"] = slope_candidates
            state.external_data = merged
        except Exception as exc:
            merged = dict(state.external_data or {})
            merged["external_sources_error"] = str(exc)
            state.external_data = merged
        return state

