"""User feedback service for field-level corrections.

Part of the three-layer memory strategy (see docs/MEMORY_STRATEGY.md):
- Task memory: TaskState (ephemeral)
- Case memory: SessionStateService
- Domain memory: UserFeedbackService (this module) — corrections in knowledge_docs
"""

from __future__ import annotations

import hashlib
import time
from collections import Counter
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from src.core.embedding import embed_text
from src.core.pg_vector_store import PgVectorStore


class UserFeedbackService:
    """Persist and retrieve field-level correction feedback.

    Implements domain memory: stores corrections in knowledge_docs (doc_type=correction)
    for use as correction_hints in extract_fields and check_completeness.
    See docs/MEMORY_STRATEGY.md.
    """

    DOC_TYPE = "correction"

    def __init__(self) -> None:
        self._store = PgVectorStore()

    def _build_filename(self, payload: Dict[str, Any]) -> str:
        raw = (
            f"{payload.get('case_id','global')}|{payload.get('field_name','')}|"
            f"{payload.get('incorrect_value','')}|{payload.get('correct_value','')}|{time.time_ns()}"
        )
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
        return f"feedback-{payload.get('case_id', 'global')}-{digest}"

    def _build_content(self, payload: Dict[str, Any]) -> str:
        lines = [
            "feedback_type: field_correction",
            f"case_id: {payload.get('case_id') or ''}",
            f"user_phone: {payload.get('user_phone') or ''}",
            f"field: {payload.get('field_name') or ''}",
            f"incorrect: {payload.get('incorrect_value') or ''}",
            f"correct: {payload.get('correct_value') or ''}",
            f"scope: {payload.get('scope') or 'global'}",
            f"note: {payload.get('note') or ''}",
            f"source_text: {payload.get('source_text') or ''}",
        ]
        return "\n".join(lines).strip()

    async def save_feedback(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        content = self._build_content(payload)
        vector = embed_text(content)
        filename = self._build_filename(payload)
        row_id = await self._store.add_to_collection(
            PgVectorStore.COLLECTION_KNOWLEDGE_DOCS,
            {
                "doc_type": self.DOC_TYPE,
                "filename": filename,
                "approved": True,
                "content": content,
                "vector": vector,
            },
        )
        return {
            "id": row_id,
            "filename": filename,
            "doc_type": self.DOC_TYPE,
            "content": content,
        }

    async def retrieve_feedback(
        self,
        query: str,
        *,
        top_k: int = 5,
        min_similarity: float = 0.25,
    ) -> List[Dict[str, Any]]:
        rows = await self._store.retrieve_from_collection(
            PgVectorStore.COLLECTION_KNOWLEDGE_DOCS,
            query=query or "case feedback",
            top_k=top_k,
            filters={"doc_type": self.DOC_TYPE},
        )
        return [r for r in rows if float(r.get("similarity", 0.0) or 0.0) >= min_similarity]

    @staticmethod
    def parse_feedback_rule(content: str) -> Optional[Dict[str, str]]:
        if not content:
            return None
        parsed: Dict[str, str] = {}
        for line in content.splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            parsed[key.strip().lower()] = value.strip()

        field_name = parsed.get("field", "")
        correct = parsed.get("correct", "")
        if not field_name or not correct:
            return None
        return {
            "field": field_name,
            "incorrect": parsed.get("incorrect", ""),
            "correct": correct,
            "scope": parsed.get("scope", "global"),
            "note": parsed.get("note", ""),
        }

    def get_high_frequency_corrections(
        self,
        min_count: int = 3,
    ) -> List[str]:
        """Return field names that have been corrected frequently (count >= min_count)."""
        try:
            sql = text(
                "SELECT content FROM knowledge_docs_vectors "
                "WHERE doc_type = :doc_type AND (COALESCE(approved, TRUE) = TRUE)"
            )
            with self._store.engine.connect() as conn:
                rows = conn.execute(sql, {"doc_type": self.DOC_TYPE}).fetchall()
            counter: Counter[str] = Counter()
            for row in rows:
                content = row[0] if row else ""
                parsed = self.parse_feedback_rule(content)
                if parsed and parsed.get("field"):
                    counter[parsed["field"]] += 1
            return [f for f, c in counter.items() if c >= min_count]
        except Exception:
            return []

