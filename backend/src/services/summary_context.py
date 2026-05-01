from __future__ import annotations

import json
import re
from typing import Any, Dict, List


_SOURCE_LABELS = {
    "ICC": "ICC / 1823 public channel",
    "TMO": "TMO",
    "RCC": "RCC",
}


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_source_code(source: Any) -> str:
    raw = _clean(source).upper()
    return raw or "UNKNOWN"


def describe_source_channel(source: Any) -> str:
    code = normalize_source_code(source)
    return _SOURCE_LABELS.get(code, code.title() if code != "UNKNOWN" else "Unknown source")


def _indefinite_article(phrase: str) -> str:
    text = _clean(phrase).lower()
    if not text:
        return "a"
    return "an" if text[0] in {"a", "e", "i", "o", "u"} else "a"


def extract_icc_handling_department(raw_text: str) -> str:
    text = _clean(raw_text)
    if not text:
        return ""

    assignment_match = re.search(
        r"II\.\s*ASSIGNMENT HISTORY:.*?(?=\n\s*=+\s*\n|\Z)",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    block = assignment_match.group(0) if assignment_match else text

    for line in block.splitlines():
        line = line.strip()
        if not line or "Open" not in line:
            continue
        m = re.match(
            r"^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\s+Open\s+([A-Z]{2,10})\s+(.+)$",
            line,
        )
        if m:
            return m.group(2).strip()

    fallback = re.search(r"Assigned to\s*[:\-]?\s*([^\n]+)", block, re.IGNORECASE)
    return fallback.group(1).strip() if fallback else ""


def assemble_summary_context(
    case_data: Dict[str, Any],
    *,
    raw_text: str = "",
    candidate_summary: str = "",
) -> Dict[str, Any]:
    data = dict(case_data or {})
    source_code = normalize_source_code(data.get("B_source"))
    source_channel = describe_source_channel(source_code)

    caller_name = _clean(data.get("E_caller_name"))
    if not caller_name:
        if source_code == "ICC":
            caller_name = "anonymous public caller"
        else:
            caller_name = "unknown caller"

    routed_department = ""
    routing = data.get("department_routing")
    if isinstance(routing, dict):
        routed_department = _clean(routing.get("department"))
    elif isinstance(data.get("department"), str):
        routed_department = _clean(data.get("department"))

    handling_department = ""
    if source_code == "ICC":
        handling_department = extract_icc_handling_department(raw_text)
    if not handling_department and routed_department and routed_department not in {"MULTI", source_code, "UNKNOWN"}:
        handling_department = routed_department

    departments_involved: List[str] = []
    for value in (source_channel, handling_department, routed_department):
        clean_value = _clean(value)
        if clean_value and clean_value not in departments_involved and clean_value != "MULTI":
            departments_involved.append(clean_value)

    context = {
        "source_code": source_code,
        "source_channel": source_channel,
        "caller_name": caller_name,
        "caller_role": (
            "public caller"
            if source_code == "ICC"
            else "referring officer"
            if source_code == "TMO"
            else "caller/client"
        ),
        "case_type": _clean(data.get("D_type")) or "Unknown",
        "call_in_date": _clean(data.get("A_date_received")),
        "key_location": _clean(data.get("H_location")) or _clean(data.get("G_slope_no")),
        "specific_incident": _clean(data.get("I_nature_of_request")) or _clean(data.get("Q_case_details")),
        "subject_matter": _clean(data.get("J_subject_matter")),
        "handling_department": handling_department,
        "routed_department": routed_department,
        "departments_involved": departments_involved,
        "candidate_summary": _clean(candidate_summary),
        "role_rules": (
            "For ICC / 1823 public cases, Assignment History fields such as Dept and Assigned To "
            "describe handling / assigned departments only. They must never be treated as caller or source."
        ),
    }
    return context


def render_summary_context(context: Dict[str, Any]) -> str:
    serializable = {
        key: value
        for key, value in dict(context or {}).items()
        if value not in ("", None, [], {})
    }
    return json.dumps(serializable, ensure_ascii=False, indent=2)


def build_deterministic_summary(context: Dict[str, Any]) -> str:
    ctx = dict(context or {})
    source_code = normalize_source_code(ctx.get("source_code"))
    source_channel = _clean(ctx.get("source_channel")) or describe_source_channel(source_code)
    caller_name = _clean(ctx.get("caller_name")) or "unknown caller"
    case_type = (_clean(ctx.get("case_type")) or "case").lower()
    call_in_date = _clean(ctx.get("call_in_date")) or "an unknown date"
    incident = _clean(ctx.get("specific_incident")) or _clean(ctx.get("subject_matter")) or "an issue"
    location = _clean(ctx.get("key_location"))
    handling_department = _clean(ctx.get("handling_department"))
    departments_involved = [
        _clean(item) for item in list(ctx.get("departments_involved") or []) if _clean(item)
    ]
    article = _indefinite_article(case_type)

    if source_code == "ICC":
        lead = f"On {call_in_date}, {article} {case_type} ICC / 1823 public case was filed by {caller_name}"
    elif source_code == "TMO":
        lead = f"On {call_in_date}, {article} {case_type} TMO referral was raised by {caller_name}"
    elif source_code == "RCC":
        lead = f"On {call_in_date}, {article} {case_type} RCC case involved {caller_name}"
    else:
        lead = f"On {call_in_date}, {article} {case_type} case involved {caller_name} via {source_channel}"

    detail = f" regarding {incident}"
    if location:
        detail += f" at {location}"

    assignment = ""
    if handling_department:
        assignment = f" and was assigned to {handling_department}"

    dept_phrase = ""
    if len(departments_involved) > 1:
        dept_phrase = f"; departments involved included {', '.join(departments_involved)}"

    return f"{lead}{detail}{assignment}{dept_phrase}."


def summary_has_role_confusion(summary: str, context: Dict[str, Any]) -> bool:
    text = _clean(summary).lower()
    if not text:
        return False

    ctx = dict(context or {})
    if normalize_source_code(ctx.get("source_code")) != "ICC":
        return False

    handling_department = _clean(ctx.get("handling_department")).lower()
    caller_name = _clean(ctx.get("caller_name")).lower()

    if "caller department" in text:
        return True
    if handling_department and f"from {handling_department}" in text:
        return True
    if handling_department and f"from the {handling_department}" in text:
        return True

    if caller_name and handling_department:
        patterns = [
            rf"{re.escape(caller_name)}[^.?!]{{0,30}}from[^.?!]{{0,30}}{re.escape(handling_department)}",
            rf"(caller|complainant|public caller)[^.?!]{{0,40}}from[^.?!]{{0,30}}{re.escape(handling_department)}",
        ]
        if any(re.search(pattern, text) for pattern in patterns):
            return True

    return False
