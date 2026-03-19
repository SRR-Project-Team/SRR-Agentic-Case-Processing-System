#!/usr/bin/env python3
"""
Centralized, runtime-adjustable RAG parameters for closed-loop optimization.

Used by _build_enhanced_chat_context and RAGContextBuilder instead of hardcoded values.
"""


class AdaptiveRAGConfig:
    """Centralized RAG parameters for retrieval and filtering."""

    def __init__(self) -> None:
        # Retrieval score thresholds (below = filtered out)
        self.min_score_historical = 0.50
        self.min_score_tree = 0.35
        self.min_score_knowledge = 0.50

        # Max docs per source
        self.max_historical_docs = 5
        self.max_tree_docs = 8
        self.max_knowledge_docs = 3

        # Quality alert thresholds (for logging)
        self.quality_alert_floor = 0.40
        self.latency_alert_ms = 12000


# Singleton instance
_config: AdaptiveRAGConfig | None = None


def get_adaptive_rag_config() -> AdaptiveRAGConfig:
    """Return the shared AdaptiveRAGConfig instance."""
    global _config
    if _config is None:
        _config = AdaptiveRAGConfig()
    return _config
