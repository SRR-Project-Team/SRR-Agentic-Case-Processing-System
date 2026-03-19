#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hybrid search: vector recall + weighted rerank for similar historical cases.

Stage 1: Vector retrieval from historical_cases_vectors (top_k=100).
Stage 2: Weighted similarity rerank using HistoricalCaseMatcher._calculate_similarity.
"""
from typing import Dict, Any, List, Optional

from src.core.pg_vector_store import PgVectorStore
from utils.slope_location_mapper import normalize_slope_core


def _vector_record_to_historical_case(rec: dict) -> dict:
    """Map vector store record to historical case dict for scoring."""
    return {
        "C_case_number": rec.get("case_number") or "",
        "H_location": rec.get("location") or "",
        "G_slope_no": rec.get("slope_no") or "",
        "J_subject_matter": "",
        "E_caller_name": "",
        "F_contact_no": "",
    }


def _vector_record_to_case_response(rec: dict) -> dict:
    """Map vector store record to API response case shape."""
    source = rec.get("source") or ""
    data_source = "Slopes Complaints 2021" if "slopes" in source else "SRR Data 2021-2024"
    return {
        "A_date_received": "",
        "C_case_number": rec.get("case_number") or "",
        "B_source": rec.get("source") or "",
        "G_slope_no": rec.get("slope_no") or "",
        "H_location": rec.get("location") or "",
        "I_nature_of_request": (rec.get("content") or "")[:500],
        "J_subject_matter": "",
        "data_source": data_source,
    }


class HybridSearchService:
    """Hybrid search: vector recall + weighted rerank."""

    def __init__(self, vector_client: PgVectorStore, weight_matcher):
        self.vector_client = vector_client
        self.weight_matcher = weight_matcher

    def _build_search_text(self, current_case: dict) -> str:
        """Build text for vector query from current case."""
        parts = [
            current_case.get("H_location") or "",
            current_case.get("G_slope_no") or "",
            current_case.get("J_subject_matter") or "",
            current_case.get("I_nature_of_request") or "",
            current_case.get("E_caller_name") or "",
        ]
        return " ".join(p for p in parts if p).strip() or "case"

    def _historical_row_to_aq_like(self, row: dict) -> dict:
        """Map historical_cases row to A-Q-like dict for few-shot."""
        return {
            "A_date_received": row.get("date_received") or "",
            "B_source": row.get("source") or "",
            "C_case_number": row.get("case_number") or "",
            "D_type": row.get("case_type") or "General",
            "E_caller_name": row.get("caller_name") or "",
            "F_contact_no": row.get("contact_no") or "",
            "G_slope_no": row.get("slope_no") or "",
            "H_location": row.get("location") or "",
            "I_nature_of_request": row.get("nature") or "",
            "J_subject_matter": row.get("subject") or "",
            "Q_case_details": (row.get("inquiry") or "") + " " + (row.get("remarks") or ""),
        }

    async def find_similar_by_raw_content(
        self,
        raw_content: str,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Find similar historical cases by raw content (for few-shot before extraction).

        Uses vector search on raw_content, then loads full rows from historical_cases.
        Returns list of A-Q-like dicts for few-shot injection.
        """
        search_text = (raw_content or "")[:2000].strip()
        if not search_text:
            return []
        try:
            candidates = await self.vector_client.retrieve_from_collection(
                PgVectorStore.COLLECTION_HISTORICAL_CASES,
                search_text,
                top_k=limit * 2,
                filters=None,
            )
        except Exception:
            return []
        if not candidates:
            return []
        case_ids = [c.get("case_id") for c in candidates if c.get("case_id")]
        if not case_ids:
            return []
        try:
            from sqlalchemy import text
            with self.vector_client.engine.connect() as conn:
                placeholders = ", ".join(f":c{i}" for i in range(len(case_ids)))
                params = {f"c{i}": cid for i, cid in enumerate(case_ids)}
                rows = conn.execute(
                    text(
                        f"SELECT case_id, source, case_number, date_received, location, "
                        f"slope_no, caller_name, contact_no, case_type, nature, subject, inquiry, remarks "
                        f"FROM historical_cases WHERE case_id IN ({placeholders})"
                    ),
                    params,
                ).mappings().all()
        except Exception:
            return []
        id_to_row = {r["case_id"]: dict(r) for r in rows}
        result = []
        for c in candidates[:limit]:
            cid = c.get("case_id")
            if cid and cid in id_to_row:
                result.append(self._historical_row_to_aq_like(id_to_row[cid]))
        return result

    async def find_similar_cases(
        self,
        current_case: dict,
        limit: int = 10,
        min_similarity: float = 0.3,
        vector_top_k: int = 100,
        override: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Find similar historical cases: vector recall then weighted rerank.

        Args:
            current_case: Current case dict (e.g. H_location, G_slope_no, J_subject_matter).
            limit: Max results to return.
            min_similarity: Minimum weighted score to include.
            vector_top_k: Number of candidates to retrieve from vector store for rerank.

        Returns:
            List of dicts: case, similarity_score, is_potential_duplicate, match_details, data_source.
        """
        override = override or {}
        strategy = override.get("strategy", "vector")
        search_text = self._build_search_text(current_case)
        slope_raw = (current_case.get("G_slope_no") or "").strip() or None
        slope_no = normalize_slope_core(slope_raw) or slope_raw if slope_raw else None
        filters = {"slope_no": slope_no} if slope_no else None

        if strategy == "bm25_keyword":
            candidates = self._keyword_search_sync(
                current_case, vector_top_k
            )
            if not candidates:
                candidates = await self.vector_client.retrieve_from_collection(
                    PgVectorStore.COLLECTION_HISTORICAL_CASES,
                    search_text,
                    top_k=vector_top_k,
                    filters=filters,
                )
        else:
            candidates = await self.vector_client.retrieve_from_collection(
                PgVectorStore.COLLECTION_HISTORICAL_CASES,
                search_text,
                top_k=vector_top_k,
                filters=filters,
            )
        if not candidates:
            return []

        # Get current case number for filtering
        current_case_number = current_case.get('C_case_number', '').strip()

        scored = []
        for c in candidates:
            historical_for_score = _vector_record_to_historical_case(c)
            
            # Skip if same case number (same case, not similar case)
            hist_case_number = historical_for_score.get('C_case_number', '').strip()
            if current_case_number and hist_case_number and \
               current_case_number == hist_case_number:
                continue
            
            score, details = self.weight_matcher._calculate_similarity(
                current_case, historical_for_score
            )
            if score < min_similarity:
                continue
            case_response = _vector_record_to_case_response(c)
            scored.append({
                "case": case_response,
                "similarity_score": score,
                "is_potential_duplicate": score >= 0.70,
                "match_details": details,
                "data_source": case_response.get("data_source", "historical"),
            })
        scored.sort(key=lambda x: x["similarity_score"], reverse=True)
        return scored[:limit]

    def _keyword_search_sync(
        self, current_case: dict, limit: int
    ) -> List[Dict[str, Any]]:
        """Keyword-based fallback when strategy=bm25_keyword."""
        from sqlalchemy import text
        keywords = [
            (current_case.get("H_location") or "").strip(),
            (current_case.get("G_slope_no") or "").strip(),
            (current_case.get("J_subject_matter") or "").strip(),
        ]
        keywords = [k for k in keywords if k]
        if not keywords:
            return []
        try:
            table = "historical_cases_vectors"
            conditions = " OR ".join(
                f"content LIKE :kw{i}" for i in range(len(keywords))
            )
            params = {f"kw{i}": f"%{kw}%" for i, kw in enumerate(keywords)}
            sql = text(
                f"SELECT id, case_id, case_number, location, slope_no, content, source "
                f"FROM {table} WHERE {conditions} LIMIT :lim"
            )
            params["lim"] = limit * 2
            with self.vector_client.engine.connect() as conn:
                rows = conn.execute(sql, params).mappings().all()
            return [
                {
                    "case_number": r.get("case_number"),
                    "location": r.get("location"),
                    "slope_no": r.get("slope_no"),
                    "content": r.get("content"),
                    "source": r.get("source"),
                }
                for r in rows
            ]
        except Exception:
            return []


_hybrid_service: Optional[HybridSearchService] = None


def init_hybrid_search_service(vector_client: PgVectorStore, weight_matcher) -> None:
    """Initialize the global hybrid search service."""
    global _hybrid_service
    _hybrid_service = HybridSearchService(vector_client, weight_matcher)


def get_hybrid_search_service() -> HybridSearchService:
    """Get the global hybrid search service. Must call init_hybrid_search_service first."""
    if _hybrid_service is None:
        raise RuntimeError(
            "Hybrid search service not initialized. Call init_hybrid_search_service() first."
        )
    return _hybrid_service
