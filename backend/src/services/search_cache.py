#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Query cache for similar-case search results (max 100 entries).
"""
import hashlib
import json
from typing import Any, Dict, Optional

_MAX_SIZE = 100
_cache: Dict[str, Any] = {}
_cache_order: list = []


def _cache_key(case_data: dict, limit: int, min_similarity: float) -> str:
    """Build a hashable cache key from request params."""
    canonical = json.dumps(
        {
            "H_location": case_data.get("H_location"),
            "G_slope_no": case_data.get("G_slope_no"),
            "J_subject_matter": case_data.get("J_subject_matter"),
            "E_caller_name": case_data.get("E_caller_name"),
            "I_nature_of_request": (case_data.get("I_nature_of_request") or "")[:200],
            "limit": limit,
            "min_similarity": min_similarity,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def get_cached_response(case_data: dict, limit: int, min_similarity: float) -> Optional[dict]:
    """Return cached full response dict if present."""
    key = _cache_key(case_data, limit, min_similarity)
    if key in _cache:
        if key in _cache_order:
            _cache_order.remove(key)
        _cache_order.append(key)
        out = dict(_cache[key])
        out["from_cache"] = True
        return out
    return None


def set_cached_response(
    case_data: dict, limit: int, min_similarity: float, response: dict
) -> None:
    """Store full response in cache (evict oldest if over max size)."""
    key = _cache_key(case_data, limit, min_similarity)
    if key in _cache_order:
        _cache_order.remove(key)
    _cache_order.append(key)
    _cache[key] = dict(response)
    while len(_cache) > _MAX_SIZE and _cache_order:
        old = _cache_order.pop(0)
        _cache.pop(old, None)


def cache_stats() -> dict:
    """Return cache stats for monitoring."""
    return {"size": len(_cache), "max_size": _MAX_SIZE}
