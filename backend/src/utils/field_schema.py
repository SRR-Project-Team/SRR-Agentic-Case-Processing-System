"""
Schema-driven A-Q field definitions for extraction and validation.

Loads aq_fields_schema.json and provides:
- schema_to_llm_prompt_block() for LLM extraction prompts
- schema_to_validation_rules() for check_completeness
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

_SCHEMA_CACHE: Optional[Dict[str, Any]] = None


def _schema_path() -> Path:
    backend = Path(__file__).resolve().parent.parent.parent
    return backend / "models" / "schema" / "aq_fields_schema.json"


def load_schema() -> Dict[str, Any]:
    """Load and parse A-Q schema from JSON."""
    global _SCHEMA_CACHE
    if _SCHEMA_CACHE is not None:
        return _SCHEMA_CACHE
    path = _schema_path()
    if not path.exists():
        _SCHEMA_CACHE = {}
        return _SCHEMA_CACHE
    try:
        with open(path, "r", encoding="utf-8") as f:
            _SCHEMA_CACHE = json.load(f) or {}
        return _SCHEMA_CACHE
    except Exception:
        _SCHEMA_CACHE = {}
        return _SCHEMA_CACHE


def get_field_def(field_name: str) -> Optional[Dict[str, Any]]:
    """Get schema definition for a field."""
    schema = load_schema()
    return schema.get(field_name)


def schema_to_llm_prompt_block(
    *,
    include_classification: bool = True,
    dtype_rules: Optional[str] = None,
    subject_categories: Optional[str] = None,
) -> str:
    """
    Generate EXTRACTION RULES section from schema for LLM prompt.

    Returns a string suitable for inclusion in extract_fields_from_text prompt.
    """
    schema = load_schema()
    if not schema:
        return ""

    lines = ["EXTRACTION RULES (from schema):"]
    for key, defn in schema.items():
        if not isinstance(defn, dict):
            continue
        ftype = defn.get("type", "string")
        hint = defn.get("source_hint", "")
        fallback = defn.get("fallback", "")
        values = defn.get("values", [])
        if values:
            lines.append(f"- {key}: {ftype} from {hint}; values: {values}; fallback: {fallback}")
        else:
            lines.append(f"- {key}: {ftype} from {hint}; fallback: {fallback}")
        lines.append("")

    if include_classification and (dtype_rules or subject_categories):
        lines.append("CLASSIFICATION RULES:")
        if dtype_rules:
            lines.append(f"D_type:\n{dtype_rules}")
        if subject_categories:
            lines.append(f"J_subject_matter (based on I_nature_of_request):\n{subject_categories}")

    return "\n".join(lines).strip()


def schema_to_validation_rules() -> List[Dict[str, Any]]:
    """
    Generate validation rules from schema for check_completeness.

    Returns list of dicts: {field, type, pattern?, values?, required?}
    """
    schema = load_schema()
    rules = []
    for key, defn in schema.items():
        if not isinstance(defn, dict):
            continue
        rule = {"field": key}
        rule["required"] = defn.get("required", False)
        rule["type"] = defn.get("type", "string")
        if "pattern" in defn:
            rule["pattern"] = defn["pattern"]
        if "values" in defn:
            rule["values"] = set(defn["values"])
        rules.append(rule)
    return rules


def get_required_fields_from_schema() -> List[str]:
    """Return list of required field names from schema."""
    schema = load_schema()
    return [k for k, v in schema.items() if isinstance(v, dict) and v.get("required", False)]


def get_enum_values(field_name: str) -> Optional[List[str]]:
    """Return allowed enum values for a field, or None if not enum."""
    defn = get_field_def(field_name)
    if not defn or defn.get("type") != "enum":
        return None
    return defn.get("values")


def get_pattern(field_name: str) -> Optional[str]:
    """Return regex pattern for a field, or None."""
    defn = get_field_def(field_name)
    if not defn:
        return None
    return defn.get("pattern")
