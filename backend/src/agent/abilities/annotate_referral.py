from __future__ import annotations

import re
from typing import Any, Dict, List

from agent.abilities.base import register_ability
from agent.task_state import TaskState

_ASSIGNMENT_BLOCK = re.compile(
    r"Assignment History.*?(?=Contact History|$)",
    re.DOTALL | re.IGNORECASE,
)

_CONTACT_BLOCK = re.compile(
    r"Contact History.*?(?=Assignment History|$)",
    re.DOTALL | re.IGNORECASE,
)

_DEPT_PATTERN = re.compile(
    r"(?:Assigned to|Transfer(?:red)? to|Referred to)\s*[:\-]?\s*(.+)",
    re.IGNORECASE,
)

_NON_ASD_DEPTS = {"HyD", "CEDD", "DSD", "LCSD", "WSD", "BD", "EPD", "FEHD", "TD"}


@register_ability
class AnnotateReferralAbility:
    """Extract cross-department referral history from 1823 TXT content."""

    name = "annotate_referral"
    required_fields: List[str] = []

    async def execute(self, state: TaskState) -> TaskState:
        text = state.raw_content or ""
        if not text.strip():
            return state

        annotations: List[Dict[str, Any]] = []

        assignment_match = _ASSIGNMENT_BLOCK.search(text)
        if assignment_match:
            block = assignment_match.group(0)
            for dept_match in _DEPT_PATTERN.finditer(block):
                dept_raw = dept_match.group(1).strip().rstrip(".")
                annotations.append({
                    "type": "assignment",
                    "department": dept_raw,
                    "is_non_asd": any(d.lower() in dept_raw.lower() for d in _NON_ASD_DEPTS),
                })

        contact_match = _CONTACT_BLOCK.search(text)
        if contact_match:
            block = contact_match.group(0)
            for dept_match in _DEPT_PATTERN.finditer(block):
                dept_raw = dept_match.group(1).strip().rstrip(".")
                annotations.append({
                    "type": "contact",
                    "department": dept_raw,
                    "is_non_asd": any(d.lower() in dept_raw.lower() for d in _NON_ASD_DEPTS),
                })

        if annotations:
            state.has_referral_history = True
            state.referral_annotations = annotations

        return state
