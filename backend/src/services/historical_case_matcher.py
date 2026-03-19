#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Historical Case Matcher Service

Provides intelligent matching of new complaints against historical cases
stored in the PostgreSQL `historical_cases` and `tree_inventory` tables.

Data Sources (all loaded from PostgreSQL):
- historical_cases  (~4,144 rows from Slopes 2021 + SRR 2021-2024)
- tree_inventory    (~32,405 rows)
"""

import os
import re
from typing import Dict, List, Any, Optional, Tuple
from difflib import SequenceMatcher

from sqlalchemy import create_engine, text

from utils.slope_location_mapper import normalize_slope_core


class HistoricalCaseMatcher:
    WEIGHT_LOCATION = 0.40
    WEIGHT_SLOPE_TREE = 0.30
    WEIGHT_SUBJECT = 0.15
    WEIGHT_CALLER_NAME = 0.10
    WEIGHT_CALLER_PHONE = 0.05

    def __init__(self, data_dir: str = "", db_path: str = ""):
        self.data_dir = data_dir
        self._engine = None
        self._data_loaded = False
        self._historical_cases: List[Dict[str, Any]] = []
        self.location_slope_mapping: Dict[str, List[str]] = {}
        print("✅ Historical Case Matcher initialized (data will load on first use)")
    
    def _get_engine(self):
        if self._engine is None:
            from config.settings import DATABASE_URL
            url = os.getenv("DATABASE_URL", DATABASE_URL)
            connect_args = {}
            if "postgresql" in url:
                connect_args = {"options": "-c timezone=Asia/Shanghai"}
            self._engine = create_engine(url, pool_pre_ping=True, connect_args=connect_args)
        return self._engine

    def _load_historical_data(self):
        engine = self._get_engine()
        with engine.connect() as conn:
            rows = conn.execute(text("SELECT * FROM historical_cases")).mappings().all()
        self._historical_cases = []
        for r in rows:
            self._historical_cases.append({
                "case_id": r["case_id"],
                "A_date_received": r.get("date_received", ""),
                "C_case_number": r.get("case_number", ""),
                "B_source": r.get("source", ""),
                "D_type": r.get("case_type", ""),
                "G_slope_no": r.get("slope_no", ""),
                "H_location": r.get("location", ""),
                "E_caller_name": r.get("caller_name", ""),
                "F_contact_no": r.get("contact_no", ""),
                "I_nature_of_request": r.get("nature", "") or r.get("inquiry", ""),
                "J_subject_matter": r.get("subject", ""),
                "remarks": r.get("remarks", ""),
                "data_source": "Slopes Complaints 2021" if "slopes" in (r.get("source") or "") else "SRR Data 2021-2024",
            })
        print(f"📂 Loaded {len(self._historical_cases)} historical cases from DB")

    def _ensure_data_loaded(self):
        if self._data_loaded:
            return
        self._load_historical_data()
        self.location_slope_mapping = self._build_location_slope_mapping()
        self._data_loaded = True
        print(f"✅ Historical data loaded: {len(self._historical_cases):,} cases")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def find_similar_cases(
        self,
        current_case: Dict[str, Any],
        limit: int = 10,
        min_similarity: float = 0.3,
    ) -> List[Dict[str, Any]]:
        self._ensure_data_loaded()
        current_case_number = (current_case.get("C_case_number") or "").strip()
        results = []

        for hist in self._historical_cases:
            hist_case_number = (hist.get("C_case_number") or "").strip()
            if current_case_number and hist_case_number and current_case_number == hist_case_number:
                continue
            score, details = self._calculate_similarity(current_case, hist)
            if score >= min_similarity:
                results.append({
                    "case": hist,
                    "similarity_score": score,
                    "is_potential_duplicate": score >= 0.70,
                    "match_details": details,
                    "data_source": hist.get("data_source", ""),
                })

        results.sort(key=lambda x: x["similarity_score"], reverse=True)
        return results[:limit]

    def get_tree_info(self, slope_no: str) -> List[Dict[str, Any]]:
        """Get trees on a slope from tree_inventory table."""
        if not slope_no:
            return []
        try:
            engine = self._get_engine()
            with engine.connect() as conn:
                rows = conn.execute(
                    text("SELECT * FROM tree_inventory WHERE slope_no = :slope_no ORDER BY tree_no"),
                    {"slope_no": slope_no},
                ).mappings().all()
            return [
                {
                    "tree_id": f"{r['slope_no']} {r['tree_no']}" if r.get("tree_no") else r.get("slope_no", ""),
                    "tree_no": r.get("tree_no", ""),
                    "slope_no": r.get("slope_no", ""),
                    "species": r.get("scientific_name", ""),
                    "chinese_name": r.get("chinese_name", ""),
                    "dbh": r.get("dbh_mm"),
                    "height": r.get("height_m"),
                    "health": r.get("health", ""),
                    "classification": r.get("classification", ""),
                    "form": r.get("form", ""),
                }
                for r in rows
            ]
        except Exception as e:
            print(f"⚠️ get_tree_info error: {e}")
            return []

    def get_case_statistics(
        self,
        location: str = None,
        slope_no: str = None,
        venue: str = None,
    ) -> Dict[str, Any]:
        self._ensure_data_loaded()
        matching = [
            h for h in self._historical_cases
            if self._matches_filters_dict(h, location, slope_no, venue)
        ]

        stats = {
            "total_cases": len(matching),
            "date_range": self._get_date_range(matching),
            "subject_matter_breakdown": self._group_by(matching, "J_subject_matter"),
            "case_type_breakdown": self._group_by(matching, "D_type"),
            "location_breakdown": self._group_by(matching, "H_location"),
            "slope_breakdown": self._group_by(matching, "G_slope_no"),
            "data_source_breakdown": self._group_by(matching, "data_source"),
            "is_frequent_location": len(matching) >= 5,
            "is_frequent_slope": len(matching) >= 3,
        }
        return stats
    
    def get_slopes_for_location(self, location: str) -> List[str]:
        self._ensure_data_loaded()
        if not location:
            return []
        location_norm = self._normalize_text(location)
        slopes = set()
        if location_norm in self.location_slope_mapping:
            slopes.update(self.location_slope_mapping[location_norm])
        for known, slope_list in self.location_slope_mapping.items():
            if location_norm in known or known in location_norm:
                slopes.update(slope_list)
        return list(slopes)
    
    # ------------------------------------------------------------------
    # Similarity helpers
    # ------------------------------------------------------------------

    def _calculate_similarity(
        self, current: Dict[str, Any], historical: Dict[str, Any]
    ) -> Tuple[float, Dict[str, Any]]:
        loc = self._match_location(current.get("H_location"), historical.get("H_location"))
        slope = self._match_slope_tree(current.get("G_slope_no"), historical.get("G_slope_no"))
        subj = self._match_subject(current.get("J_subject_matter"), historical.get("J_subject_matter"))
        name = self._match_caller_name(current.get("E_caller_name"), historical.get("E_caller_name"))
        phone = self._match_phone(current.get("F_contact_no"), historical.get("F_contact_no"))

        total = (
            loc * self.WEIGHT_LOCATION
            + slope * self.WEIGHT_SLOPE_TREE
            + subj * self.WEIGHT_SUBJECT
            + name * self.WEIGHT_CALLER_NAME
            + phone * self.WEIGHT_CALLER_PHONE
        )
        details = {
            "location_match": loc,
            "slope_tree_match": slope,
            "subject_match": subj,
            "caller_name_match": name,
            "caller_phone_match": phone,
            "component_scores": {
                "location": loc * self.WEIGHT_LOCATION,
                "slope_tree": slope * self.WEIGHT_SLOPE_TREE,
                "subject": subj * self.WEIGHT_SUBJECT,
                "caller_name": name * self.WEIGHT_CALLER_NAME,
                "caller_phone": phone * self.WEIGHT_CALLER_PHONE,
            },
            "total_score": total,
        }
        return total, details

    def _match_location(self, loc1, loc2) -> float:
        if not loc1 or not loc2:
            return 0.0
        return SequenceMatcher(None, self._normalize_text(loc1), self._normalize_text(loc2)).ratio()

    def _match_slope_tree(self, s1, s2) -> float:
        if not s1 or not s2:
            return 0.0
        # 使用 normalize_slope_core 使 11SW-A/FR24(3) 与 11SW-A/FR24 视为同一棵树
        c1 = normalize_slope_core(str(s1)).strip().upper()
        c2 = normalize_slope_core(str(s2)).strip().upper()
        return 1.0 if c1 == c2 else 0.0

    def _match_subject(self, s1, s2) -> float:
        if not s1 or not s2:
            return 0.0
        w1 = set(self._normalize_text(s1).split())
        w2 = set(self._normalize_text(s2).split())
        union = len(w1 | w2)
        return len(w1 & w2) / union if union else 0.0

    def _match_caller_name(self, n1, n2) -> float:
        if not n1 or not n2:
            return 0.0
        return SequenceMatcher(None, self._normalize_text(n1), self._normalize_text(n2)).ratio()

    def _match_phone(self, p1, p2) -> float:
        if not p1 or not p2:
            return 0.0
        d1 = re.sub(r"\D", "", str(p1))
        d2 = re.sub(r"\D", "", str(p2))
        if d1 == d2:
            return 1.0
        if len(d1) >= 8 and len(d2) >= 8 and d1[-8:] == d2[-8:]:
            return 1.0
        return 0.0

    # ------------------------------------------------------------------
    # Filter / mapping helpers
    # ------------------------------------------------------------------

    def _matches_filters_dict(self, h: Dict, location, slope_no, venue) -> bool:
        if location:
            loc = h.get("H_location", "")
            if not loc or location.lower() not in loc.lower():
                return False
        if slope_no:
            sl = h.get("G_slope_no", "")
            if not sl or slope_no.lower() not in sl.lower():
                return False
        if venue:
            loc = h.get("H_location", "")
            if not loc or venue.lower() not in loc.lower():
                return False
        return True
    
    def _build_location_slope_mapping(self) -> Dict[str, List[str]]:
        mapping: Dict[str, set] = {}
        for h in self._historical_cases:
            slope_no = h.get("G_slope_no", "")
            location = h.get("H_location", "")
            if slope_no and location:
                slope_norm = self._normalize_slope(slope_no)
                loc_norm = self._normalize_text(location)
                if loc_norm:
                    mapping.setdefault(loc_norm, set()).add(slope_norm)
        return {k: list(v) for k, v in mapping.items()}

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def _normalize_text(self, val) -> str:
        if not val:
            return ""
        return str(val).lower().strip()

    def _normalize_slope(self, val) -> str:
        if not val:
            return ""
        return re.sub(r"[\s\-/]", "", str(val).upper())

    def _get_date_range(self, cases: List[Dict]) -> Dict[str, str]:
        dates = [c.get("A_date_received") for c in cases if c.get("A_date_received")]
        if not dates:
            return {"earliest": "N/A", "latest": "N/A"}
        return {"earliest": min(dates), "latest": max(dates)}
    
    def _group_by(self, cases: List[Dict], field: str) -> Dict[str, int]:
        groups: Dict[str, int] = {}
        for c in cases:
            val = c.get(field, "Unknown")
            if val:
                groups[val] = groups.get(val, 0) + 1
        return groups


# ======================================================================
# Global singleton
# ======================================================================

_matcher_instance = None


def init_historical_matcher(data_dir: str = "", db_path: str = ""):
    global _matcher_instance
    _matcher_instance = HistoricalCaseMatcher(data_dir, db_path)


def get_historical_matcher() -> HistoricalCaseMatcher:
    global _matcher_instance
    if _matcher_instance is None:
        current_file = os.path.abspath(__file__)
        backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(current_file)))
        data_dir = os.path.join(backend_dir, "data")
        print("🔄 Lazy-loading historical case matcher (first request)...", flush=True)
        _matcher_instance = HistoricalCaseMatcher(data_dir)
        print("✅ Historical case matcher lazy-load complete", flush=True)
    return _matcher_instance
