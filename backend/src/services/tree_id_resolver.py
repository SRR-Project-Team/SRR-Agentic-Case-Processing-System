#!/usr/bin/env python3
"""Tree ID extraction, normalization, and database lookup utilities.

Tree ID = Slope No + Tree No  (e.g. "11SW-C/F48 TS013")
The same tree can also be referenced via Slope ID: "SA2081 TS013".
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import create_engine, text


class TreeIDResolver:
    """Resolve Tree ID from free text and case payloads."""

    _TREE_NO_PATTERNS: List[re.Pattern[str]] = [
        re.compile(r"(?i)\btree\s*(?:id|no\.?|number)\s*[:#]?\s*([A-Z]{1,4}[-/]?\d{1,6})\b"),
        re.compile(r"\b(TS\d{1,6})\b", re.IGNORECASE),
    ]

    _engine = None

    @classmethod
    def _get_engine(cls):
        if cls._engine is None:
            from config.settings import DATABASE_URL
            import os
            url = os.getenv("DATABASE_URL", DATABASE_URL)
            connect_args = {}
            if "postgresql" in url:
                connect_args = {"options": "-c timezone=Asia/Shanghai"}
            cls._engine = create_engine(url, pool_pre_ping=True, connect_args=connect_args)
        return cls._engine

    def normalize(self, value: str) -> str:
        if not value:
            return ""
        return re.sub(r"[^A-Za-z0-9/-]", "", str(value).strip().upper())

    def extract_tree_no(self, text_val: str) -> Optional[str]:
        """Extract bare tree number (e.g. TS013) from free text."""
        if not text_val:
            return None
        for pattern in self._TREE_NO_PATTERNS:
            match = pattern.search(str(text_val))
            if match:
                return self.normalize(match.group(1) if match.groups() else match.group(0))
        return None

    def extract_tree_nos(self, text_val: str) -> List[str]:
        if not text_val:
            return []
        results: List[str] = []
        for pattern in self._TREE_NO_PATTERNS:
            for match in pattern.findall(str(text_val)):
                candidate = match[0] if isinstance(match, tuple) else match
                normalized = self.normalize(candidate)
                if normalized and normalized not in results:
                    results.append(normalized)
        return results

    # Keep backward-compatible alias
    extract_tree_id = extract_tree_no
    extract_tree_ids = extract_tree_nos

    def resolve_from_case(self, case_data: Dict[str, object]) -> Optional[str]:
        """Resolve full Tree ID (slope_no + tree_no) from a case dict.

        Tries direct keys first, then extracts tree_no from text fields
        and combines with G_slope_no to form the full identifier.
        """
        slope_no = str(case_data.get("G_slope_no") or "").strip()

        direct_keys: Iterable[str] = ("tree_id", "treeId", "TreeID", "tree_no", "tree_number")
        for key in direct_keys:
            value = case_data.get(key)
            if value:
                raw = self.normalize(str(value))
                if raw:
                    if " " in str(value).strip():
                        return str(value).strip().upper()
                    if slope_no:
                        return f"{slope_no} {raw}"
                    return raw

        candidate_fields = (
            "I_nature_of_request",
            "J_subject_matter",
            "Q_case_details",
            "remarks",
        )
        for key in candidate_fields:
            tree_no = self.extract_tree_no(str(case_data.get(key) or ""))
            if tree_no:
                if slope_no:
                    return f"{slope_no} {tree_no}"
                return tree_no
        return None

    def resolve_slope_id(self, slope_no: str) -> Optional[str]:
        """Look up slope_id from slope_no via the slopes table."""
        if not slope_no:
            return None
        try:
            engine = self._get_engine()
            with engine.connect() as conn:
                row = conn.execute(
                    text("SELECT slope_id FROM slopes WHERE slope_no = :slope_no"),
                    {"slope_no": slope_no},
                ).mappings().first()
                return row["slope_id"] if row else None
        except Exception:
            return None

    def resolve_slope_no(self, slope_id: str) -> Optional[str]:
        """Look up slope_no from slope_id via the slopes table."""
        if not slope_id:
            return None
        try:
            engine = self._get_engine()
            with engine.connect() as conn:
                row = conn.execute(
                    text("SELECT slope_no FROM slopes WHERE slope_id = :slope_id"),
                    {"slope_id": slope_id},
                ).mappings().first()
                return row["slope_no"] if row else None
        except Exception:
            return None

    def lookup_tree(self, slope_no: str, tree_no: str) -> Optional[Dict[str, Any]]:
        """Look up a specific tree from the tree_inventory table."""
        if not slope_no or not tree_no:
            return None
        try:
            engine = self._get_engine()
            with engine.connect() as conn:
                row = conn.execute(
                    text("""
                        SELECT * FROM tree_inventory
                        WHERE slope_no = :slope_no AND tree_no = :tree_no
                        LIMIT 1
                    """),
                    {"slope_no": slope_no, "tree_no": tree_no},
                ).mappings().first()
                if row:
                    return dict(row)
        except Exception:
            pass
        return None

    def lookup_trees_on_slope(self, slope_no: str) -> List[Dict[str, Any]]:
        """Return all trees on a given slope from the tree_inventory table."""
        if not slope_no:
            return []
        try:
            engine = self._get_engine()
            with engine.connect() as conn:
                rows = conn.execute(
                    text("SELECT * FROM tree_inventory WHERE slope_no = :slope_no ORDER BY tree_no"),
                    {"slope_no": slope_no},
                ).mappings().all()
                return [dict(r) for r in rows]
        except Exception:
            return []

    def format_full_tree_id(self, slope_no: str, tree_no: str) -> str:
        """Return the canonical full tree id string."""
        if tree_no:
            return f"{slope_no} {tree_no}".strip()
        return slope_no or ""

    def format_tree_id_with_alias(self, slope_no: str, tree_no: str) -> str:
        """Return tree id with both slope_no and slope_id forms."""
        primary = self.format_full_tree_id(slope_no, tree_no)
        slope_id = self.resolve_slope_id(slope_no)
        if slope_id and tree_no:
            return f"{primary} (aka {slope_id} {tree_no})"
        return primary
