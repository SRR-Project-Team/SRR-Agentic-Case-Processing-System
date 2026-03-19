from __future__ import annotations

import re
from typing import Any, Dict, List, Set

from agent.abilities.base import register_ability
from agent.task_state import TaskState
from services.user_feedback_service import UserFeedbackService

_REQUIRED_FIELDS = [
    "A_date_received",
    "B_source",
    "C_case_number",
    "G_slope_no",
    "H_location",
    "I_nature_of_request",
    "J_subject_matter",
]

_SLOPE_NO_PATTERN = re.compile(
    r"^\d{1,2}[A-Za-z]{2,3}[-/][A-Za-z0-9/()\-]+$"
)

_DATE_PATTERN = re.compile(
    r"^\d{1,2}-[A-Za-z]{3}-\d{4}$"
)

_D_TYPE_VALUES = {"Emergency", "Urgent", "General"}


def _get_required_fields() -> List[str]:
    """Use schema if available, else fallback to hardcoded list."""
    try:
        from utils.field_schema import get_required_fields_from_schema
        schema_fields = get_required_fields_from_schema()
        if schema_fields:
            return schema_fields
    except Exception:
        pass
    return _REQUIRED_FIELDS


def _get_d_type_values() -> set:
    """Use schema if available, else fallback to hardcoded set."""
    try:
        from utils.field_schema import get_enum_values
        values = get_enum_values("D_type")
        if values:
            return set(values)
    except Exception:
        pass
    return _D_TYPE_VALUES
_TMO_FORM_TYPES = {"form1", "form2", "hazardous", "unknown"}


@register_ability
class CheckCompletenessAbility:
    """Validate extracted fields for format and logical consistency."""

    name = "check_completeness"
    required_fields: List[str] = []

    async def execute(self, state: TaskState) -> TaskState:
        fields: Dict[str, Any] = state.fields
        errors: List[str] = []

        high_freq: Set[str] = set()
        try:
            svc = UserFeedbackService()
            high_freq = set(svc.get_high_frequency_corrections(min_count=3))
        except Exception:
            pass

        for key in _get_required_fields():
            val = fields.get(key)
            if val in (None, "", [], {}):
                errors.append(f"missing:{key}")

        slope = str(fields.get("G_slope_no") or "").strip()
        if slope and not _SLOPE_NO_PATTERN.match(slope):
            errors.append(f"format:G_slope_no invalid '{slope}'")

        a_date = str(fields.get("A_date_received") or "").strip()
        if a_date and not _DATE_PATTERN.match(a_date):
            errors.append(f"format:A_date_received '{a_date}' not dd-MMM-yyyy")

        d_type = str(fields.get("D_type") or "").strip()
        d_type_values = _get_d_type_values()
        if d_type and d_type not in d_type_values:
            errors.append(f"enum:D_type '{d_type}' not in {d_type_values}")

        if (state.source_type or "").upper() == "TMO":
            form_type = str(fields.get("tmo_form_type") or "unknown").strip().lower()
            if form_type not in _TMO_FORM_TYPES:
                errors.append(f"enum:tmo_form_type '{form_type}' not in {_TMO_FORM_TYPES}")
            if form_type == "unknown":
                errors.append("missing:tmo_form_type")
            if form_type == "form2" and not str(fields.get("G_slope_no") or "").strip():
                errors.append("rule:tmo_form2 requires G_slope_no")
            if form_type == "hazardous":
                subject = str(fields.get("J_subject_matter") or "").lower()
                if "hazardous" not in subject:
                    errors.append("rule:tmo_hazardous expects J_subject_matter contains 'Hazardous'")

        if "J_subject_matter" in high_freq:
            subject = str(fields.get("J_subject_matter") or "").strip().lower()
            if subject and len(subject) > 2:
                valid_keywords = (
                    "hazardous", "trimming", "pruning", "fallen",
                    "grass", "cutting", "erosion", "others"
                )
                if not any(kw in subject for kw in valid_keywords):
                    errors.append(
                        "rule:J_subject_matter (high-correction field) should match "
                        "categories: Hazardous Tree, Tree Trimming, Fallen Tree, Grass Cutting, "
                        "Surface Erosion, Others"
                    )
            conflicts = fields.get("tmo_form_conflicts") or []
            if not isinstance(conflicts, list):
                conflicts = [str(conflicts)]
            for idx, conflict in enumerate(conflicts, start=1):
                errors.append(f"conflict:tmo_form:{idx}:{conflict}")

        state.validation_errors = errors
        return state
