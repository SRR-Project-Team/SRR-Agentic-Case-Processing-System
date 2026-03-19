from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from agent.abilities.base import register_ability
from agent.task_state import TaskState

_DATE_FORMATS = [
    "%d-%b-%Y",
    "%d-%B-%Y",
    "%d %b %Y",
    "%d %B %Y",
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%Y-%m-%d %H:%M:%S",
]


def _parse_date(raw: str) -> Optional[datetime]:
    if not raw or not isinstance(raw, str):
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw.strip(), fmt)
        except ValueError:
            continue
    return None


def _format_dd_mmm_yyyy(dt: Optional[datetime]) -> str:
    return dt.strftime("%d-%b-%Y") if dt else ""


def _add_days(base: Optional[datetime], days: int) -> str:
    if not base:
        return ""
    return _format_dd_mmm_yyyy(base + timedelta(days=days))


_WORKS_DAYS: Dict[str, int] = {"Emergency": 1, "Urgent": 3, "General": 12}


@register_ability
class CalculateDeadlinesAbility:
    """Centralized deadline fill for K / L / M / N / O1.

    Onion-model: if the extractor already computed a value, keep it.
    Only fill when the field is empty or missing.
    ICC L/M special rule: LLM may have extracted them from "I. DUE DATE:" block.
    """

    name = "calculate_deadlines"
    required_fields: List[str] = []

    async def execute(self, state: TaskState) -> TaskState:
        fields: Dict[str, Any] = state.fields
        a_raw = str(fields.get("A_date_received") or "").strip()
        a_date = _parse_date(a_raw)
        source = (state.source_type or "").upper()
        d_type = str(fields.get("D_type") or "General").strip()

        if not a_date:
            return state

        if not fields.get("K_10day_rule_due_date"):
            fields["K_10day_rule_due_date"] = _add_days(a_date, 10)

        if source == "ICC":
            if not fields.get("L_icc_interim_due"):
                fields["L_icc_interim_due"] = _add_days(a_date, 10)
            if not fields.get("M_icc_final_due"):
                fields["M_icc_final_due"] = _add_days(a_date, 21)
        elif source == "TMO":
            if not fields.get("L_icc_interim_due"):
                fields["L_icc_interim_due"] = _add_days(a_date, 10)
            if not fields.get("M_icc_final_due"):
                fields["M_icc_final_due"] = _add_days(a_date, 21)
        else:
            if not fields.get("L_icc_interim_due"):
                fields["L_icc_interim_due"] = "N/A"
            if not fields.get("M_icc_final_due"):
                fields["M_icc_final_due"] = "N/A"

        if not fields.get("N_works_completion_due"):
            days = _WORKS_DAYS.get(d_type, 12)
            fields["N_works_completion_due"] = _add_days(a_date, days)

        if not fields.get("O1_fax_to_contractor"):
            fields["O1_fax_to_contractor"] = _format_dd_mmm_yyyy(a_date)

        return state
