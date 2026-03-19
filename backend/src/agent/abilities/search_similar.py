from __future__ import annotations

from typing import List

from agent.abilities.base import register_ability
from agent.task_state import TaskState
from services.hybrid_search_service import (
    get_hybrid_search_service,
    init_hybrid_search_service,
)
from services.historical_case_matcher import get_historical_matcher
from src.core.pg_vector_store import PgVectorStore


@register_ability
class SearchSimilarCasesAbility:
    name = "search_similar_cases"
    required_fields: List[str] = []

    async def execute(self, state: TaskState) -> TaskState:
        current_case = dict(state.fields or {})
        override = (state.external_data or {}).get("search_override") or {}
        try:
            try:
                service = get_hybrid_search_service()
            except RuntimeError:
                matcher = get_historical_matcher()
                vector_client = PgVectorStore()
                init_hybrid_search_service(vector_client, matcher)
                service = get_hybrid_search_service()

            state.similar_cases = await service.find_similar_cases(
                current_case, override=override
            )
        except Exception:
            state.similar_cases = []

        if not state.similar_cases:
            try:
                matcher = get_historical_matcher()
                state.similar_cases = matcher.find_similar_cases(
                    current_case=current_case, limit=5, min_similarity=0.3
                )
            except Exception:
                state.similar_cases = []
        return state
