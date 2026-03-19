from __future__ import annotations

from typing import Any, Dict, List

from agent.abilities.base import register_ability
from agent.task_state import TaskState
from utils.slope_location_mapper import clean_slope_number, get_location_from_slope_no
from services.tree_id_resolver import TreeIDResolver


@register_ability
class RouteDepartmentAbility:
    """Slope normalization + location fill + tree ID + department routing.

    Wraps SlopeService logic.  Extractor output is kept; this ability only
    fills blanks and adds department_routing.
    """

    name = "route_department"
    required_fields: List[str] = []

    def __init__(self) -> None:
        self._tree_resolver = TreeIDResolver()

    async def execute(self, state: TaskState) -> TaskState:
        fields: Dict[str, Any] = state.fields
        raw_slope = str(fields.get("G_slope_no") or "").strip()
        if not raw_slope:
            return state

        normalized = clean_slope_number(raw_slope) or raw_slope
        fields["G_slope_no"] = normalized

        if not fields.get("H_location"):
            loc = get_location_from_slope_no(normalized)
            if loc:
                fields["H_location"] = loc

        if not fields.get("tree_id"):
            full_tree_id = self._tree_resolver.resolve_from_case(fields)
            if full_tree_id:
                fields["tree_id"] = full_tree_id
                parts = full_tree_id.split()
                if len(parts) >= 2:
                    fields["tree_no"] = parts[-1]

        try:
            from services.slope_service import SlopeService
            svc = SlopeService()
            dept = await svc.determine_department(normalized)
            state.department_routing = dept or {}
        except Exception:
            state.department_routing = {
                "department": "unknown",
                "confidence": "low",
                "source": "error",
            }

        return state
