#!/usr/bin/env python3
"""Unified tree inventory content builder for RAG vectorization."""

from __future__ import annotations

import math
from typing import Any, Dict


def _safe_str(val: Any) -> str:
    if val is None or val == "":
        return ""
    return str(val).strip()


def build_tree_content(row: Dict[str, Any]) -> str:
    """
    Build standardized RAG content string from a tree row.

    Used by both init_vector_store (from tree_inventory table) and
    knowledge_base_service (from uploaded Excel/CSV).

    Args:
        row: Dict with keys slope_no, slope_id, tree_no, scientific_name,
             chinese_name, height_m, dbh_mm, health, classification.
             Missing/None values are handled gracefully.

    Returns:
        Content string for embedding and retrieval.
    """
    slope_no = _safe_str(row.get("slope_no"))
    slope_id = _safe_str(row.get("slope_id"))
    tree_no = _safe_str(row.get("tree_no"))
    tree_id_full = f"{slope_no} {tree_no}".strip() if tree_no else slope_no

    scientific_name = _safe_str(row.get("scientific_name"))
    chinese_name = _safe_str(row.get("chinese_name"))
    species_str = f"{scientific_name} ({chinese_name})" if chinese_name else (scientific_name or "N/A")

    height = row.get("height_m")
    dbh = row.get("dbh_mm")
    if height is not None and isinstance(height, float) and math.isnan(height):
        height = None
    if dbh is not None and isinstance(dbh, float) and math.isnan(dbh):
        dbh = None
    height_str = f"{height}m" if height is not None else "N/A"
    dbh_str = f"{dbh}mm" if dbh is not None else "N/A"

    health = _safe_str(row.get("health"))
    classification = _safe_str(row.get("classification"))

    return (
        f"Tree ID: {tree_id_full} (Slope ID: {slope_id}). "
        f"Species: {species_str}. "
        f"Height: {height_str}. DBH: {dbh_str}. "
        f"Health: {health}. Classification: {classification}"
    )
