#!/usr/bin/env python3
"""Build compact RAG context from multi-source retrieval results."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple

from services.tree_id_resolver import TreeIDResolver
from services.adaptive_rag_config import get_adaptive_rag_config


class RAGContextBuilder:
    """Compose an LLM-friendly context string."""

    def __init__(self) -> None:
        self.tree_resolver = TreeIDResolver()
        self._config = get_adaptive_rag_config()

    def _filter_by_score(
        self, docs: Iterable[Dict[str, Any]], min_score: float
    ) -> List[Dict[str, Any]]:
        return [
            d for d in docs
            if float(d.get("similarity", 0.0) or 0.0) >= min_score and d.get("content")
        ]

    def _to_metric(self, source: str, docs: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        metrics: List[Dict[str, Any]] = []
        for idx, doc in enumerate(docs, start=1):
            content = (doc.get("content") or "").strip()
            if not content:
                continue
            similarity = float(doc.get("similarity", 0.0) or 0.0)
            metrics.append(
                {
                    "source": source,
                    "doc_id": str(doc.get("id") or doc.get("case_id") or f"{source}-{idx}"),
                    "doc_title": (doc.get("title") or content[:80]).strip(),
                    "similarity_score": similarity,
                    "relevance_score": similarity,
                    "used_in_answer": False,
                    "snippet": content[:320],
                }
            )
        return metrics

    def build(
        self,
        query: str,
        case_context: Dict[str, Any],
        historical: Iterable[Dict[str, Any]],
        trees: Iterable[Dict[str, Any]],
        knowledge: Iterable[Dict[str, Any]],
    ) -> str:
        full_tree_id = self.tree_resolver.resolve_from_case(case_context or {})
        sections: List[str] = [f"User query: {query}"]

        if full_tree_id:
            parts = full_tree_id.split()
            slope_no = parts[0] if len(parts) >= 2 else ""
            tree_no = parts[-1] if len(parts) >= 2 else ""
            alias = self.tree_resolver.format_tree_id_with_alias(slope_no, tree_no) if slope_no else full_tree_id
            sections.append(f"Resolved Tree ID: {alias}")

            tree_detail = self.tree_resolver.lookup_tree(slope_no, tree_no) if slope_no and tree_no else None
            if tree_detail:
                detail_str = (
                    f"Species: {tree_detail.get('scientific_name', '')} ({tree_detail.get('chinese_name', '')}), "
                    f"Height: {tree_detail.get('height_m', '')}m, DBH: {tree_detail.get('dbh_mm', '')}mm, "
                    f"Health: {tree_detail.get('health', '')}, Classification: {tree_detail.get('classification', '')}, "
                    f"Defect trunk: {tree_detail.get('defect_trunk', '')}, "
                    f"Defect branch: {tree_detail.get('defect_branch_crown', '')}"
                )
                sections.append(f"Tree detail: {detail_str}")

        cfg = self._config
        historical_docs = self._filter_by_score(historical, min_score=cfg.min_score_historical)
        tree_docs = self._filter_by_score(trees, min_score=cfg.min_score_tree)
        knowledge_docs = self._filter_by_score(knowledge, min_score=cfg.min_score_knowledge)

        if historical_docs:
            sections.append(
                "Historical cases:\n" + "\n".join(
                    f"- {d.get('content', '')[:500]}" for d in historical_docs[: cfg.max_historical_docs]
                )
            )
        if tree_docs:
            sections.append(
                "Tree inventory:\n" + "\n".join(
                    f"- {d.get('content', '')[:500]}" for d in tree_docs[: cfg.max_tree_docs]
                )
            )
        if knowledge_docs:
            sections.append(
                "Knowledge base docs:\n" + "\n".join(
                    f"- {d.get('content', '')[:500]}" for d in knowledge_docs[: cfg.max_knowledge_docs]
                )
            )
        return "\n\n".join(s for s in sections if s).strip()

    def build_with_metadata(
        self,
        query: str,
        case_context: Dict[str, Any],
        historical: Iterable[Dict[str, Any]],
        trees: Iterable[Dict[str, Any]],
        knowledge: Iterable[Dict[str, Any]],
    ) -> Tuple[str, Dict[str, Any]]:
        """Build context string and retrieval metrics for observability."""
        cfg = self._config
        historical_docs = self._filter_by_score(historical, min_score=cfg.min_score_historical)
        tree_docs = self._filter_by_score(trees, min_score=cfg.min_score_tree)
        knowledge_docs = self._filter_by_score(knowledge, min_score=cfg.min_score_knowledge)
        context = self.build(query, case_context, historical_docs, tree_docs, knowledge_docs)
        metrics = (
            self._to_metric("historical_cases", historical_docs[: cfg.max_historical_docs])
            + self._to_metric("tree_inventory", tree_docs[: cfg.max_tree_docs])
            + self._to_metric("knowledge_base", knowledge_docs[: cfg.max_knowledge_docs])
        )
        return context, {"retrieval_metrics": metrics, "total_docs_retrieved": len(metrics)}
