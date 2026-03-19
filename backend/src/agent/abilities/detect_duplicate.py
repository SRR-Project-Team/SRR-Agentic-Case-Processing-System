from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from agent.abilities.base import register_ability
from agent.task_state import TaskState

_DUP_PATTERNS = [
    re.compile(r"(?:duplicate|dup(?:licate)?)\s*(?:of|case)?\s*[:#]?\s*([A-Z0-9/\-]*\d[A-Z0-9/\-]*)", re.IGNORECASE),
    re.compile(r"\bre\b\s*[:#\-]\s*([A-Z0-9/\-]*\d[A-Z0-9/\-]*)", re.IGNORECASE),
    re.compile(r"\bref(?:erence)?\b\s*[:#\-]?\s*([A-Z0-9/\-]*\d[A-Z0-9/\-]*)", re.IGNORECASE),
    re.compile(r"重複.*?案件.*?([A-Z0-9/\-]*\d[A-Z0-9/\-]*)", re.IGNORECASE),
    re.compile(r"重复.*?案件.*?([A-Z0-9/\-]*\d[A-Z0-9/\-]*)", re.IGNORECASE),
]

_DUP_TITLE_HINTS = (
    "duplicate case",
    "repeat case",
    "re-open",
    "重複",
    "重复",
    "跟进",
    "跟進",
)

_NEW_TITLE_HINTS = (
    "new case",
    "new complaint",
    "fresh case",
    "新案件",
    "新投诉",
    "新投訴",
)


def _extract_prior_case_no(text: str) -> Optional[str]:
    for pat in _DUP_PATTERNS:
        m = pat.search(text or "")
        if m:
            return m.group(1).strip().upper()
    return None


def _contains_hint(text: str, hints: tuple[str, ...]) -> bool:
    lower = (text or "").lower()
    return any(h.lower() in lower for h in hints)


@register_ability
class DetectDuplicateAbility:
    """L3 duplicate detection via 1823 title/content parsing.

    Does NOT replace L1 (file hash at upload) or L2 (vector similarity in
    search_similar_cases).  Only adds structured annotation when the raw text
    explicitly mentions a prior case number.
    """

    name = "detect_duplicate"
    required_fields: List[str] = []

    async def execute(self, state: TaskState) -> TaskState:
        text_sources = [
            str(state.fields.get("I_nature_of_request") or ""),
            str(state.fields.get("Q_case_details") or ""),
            state.raw_content[:5000] if state.raw_content else "",
        ]
        combined = "\n".join(t for t in text_sources if t.strip())
        title = str(state.fields.get("I_nature_of_request") or "")

        prior = _extract_prior_case_no(combined)
        top_similar = (state.similar_cases or [None])[0] or {}
        top_case = (top_similar.get("case") or {}) if isinstance(top_similar, dict) else {}
        top_case_no = str(top_case.get("C_case_number") or "").strip().upper()
        top_is_dup = bool(top_similar.get("is_potential_duplicate")) if isinstance(top_similar, dict) else False
        top_score = float(top_similar.get("similarity_score") or 0.0) if isinstance(top_similar, dict) else 0.0

        if prior:
            classification = "duplicate"
        elif _contains_hint(title, _NEW_TITLE_HINTS) and not _contains_hint(title, _DUP_TITLE_HINTS):
            classification = "new_case"
        elif _contains_hint(title, _DUP_TITLE_HINTS):
            classification = "duplicate"
            if top_case_no:
                prior = top_case_no
        elif top_is_dup and top_score >= 0.8 and top_case_no:
            classification = "possible_duplicate"
            prior = top_case_no
        else:
            classification = "new_case"

        if prior:
            state.fields["_duplicate_of"] = prior
        state.fields["_case_classification"] = classification

        detection: Dict[str, Any] = {
            "is_duplicate": bool(prior),
            "classification": classification,
            "prior_case_number": prior,
            "similarity_score": round(top_score, 4) if top_score else None,
            "detection_method": "rules+similarity",
        }
        if isinstance(top_case, dict) and top_case.get("id"):
            detection["prior_case_id"] = top_case.get("id")
            state.fields["_duplicate_case_id"] = top_case.get("id")
        state.external_data["duplicate_detection"] = detection

        return state
