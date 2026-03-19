from __future__ import annotations

from typing import Any, Dict, List

from agent.abilities.base import register_ability
from agent.task_state import TaskState


_CROSS_SOURCE_MAP: Dict[str, List[str]] = {
    "G_slope_no": ["Q_case_details", "I_nature_of_request"],
    "E_caller_name": ["Q_case_details"],
    "J_subject_matter": ["I_nature_of_request", "Q_case_details"],
}


def _try_extract_slope(text: str) -> str:
    import re
    m = re.search(r"\b(\d{1,2}[A-Za-z]{2,3}[-/][A-Za-z0-9/()\-]+)\b", text or "")
    return m.group(1) if m else ""


def _fill_from_attachments(state: TaskState, filled: List[str]) -> None:
    """Fill missing fields from Vision-parsed attachments (location_plans, site_photos)."""
    attachments = (state.external_data or {}).get("attachments") or {}
    if not attachments:
        return

    fields = state.fields
    location_plans = attachments.get("location_plans") or []
    site_photos = attachments.get("site_photos") or []

    if "G_slope_no" not in filled and not fields.get("G_slope_no"):
        for item in location_plans:
            if isinstance(item, dict):
                ext = item.get("extracted") or {}
                slope = ext.get("slope_no") or ""
                if slope:
                    fields["G_slope_no"] = slope
                    filled.append("G_slope_no")
                    break
            if not fields.get("H_location") and isinstance(item, dict):
                ext = item.get("extracted") or {}
                area = ext.get("area") or ""
                road = ext.get("road") or ""
                if area or road:
                    loc = ", ".join(x for x in [area, road] if x)
                    if loc and not fields.get("H_location"):
                        fields["H_location"] = loc

    if "Q_case_details" not in filled and not fields.get("Q_case_details"):
        for item in site_photos:
            if isinstance(item, dict):
                ext = item.get("extracted") or {}
                desc = ext.get("description") or ""
                if desc:
                    existing = str(fields.get("Q_case_details") or "").strip()
                    if existing:
                        fields["Q_case_details"] = f"{existing}\n\n[現場照片描述] {desc}"
                    else:
                        fields["Q_case_details"] = f"[現場照片描述] {desc}"
                    filled.append("Q_case_details")
                    break


@register_ability
class FillMissingAbility:
    """Best-effort fill for missing fields from other available fields and attachments."""

    name = "fill_missing"
    required_fields: List[str] = []

    async def execute(self, state: TaskState) -> TaskState:
        fields: Dict[str, Any] = state.fields
        filled: List[str] = []

        _fill_from_attachments(state, filled)

        for target_key, source_keys in _CROSS_SOURCE_MAP.items():
            if target_key in filled or fields.get(target_key):
                continue
            for src_key in source_keys:
                src_val = str(fields.get(src_key) or "").strip()
                if not src_val:
                    continue
                if target_key == "G_slope_no":
                    extracted = _try_extract_slope(src_val)
                    if extracted:
                        fields[target_key] = extracted
                        filled.append(target_key)
                        break
                else:
                    if len(src_val) > 2:
                        fields[target_key] = src_val[:200]
                        filled.append(target_key)
                        break

        state.missing_fields = [
            k for k in state.missing_fields if k not in filled
        ]
        return state
