from __future__ import annotations

from typing import Any, Dict, List

from agent.abilities.base import register_ability
from agent.task_state import TaskState
from services.rag_context_builder import RAGContextBuilder


@register_ability
class SearchKnowledgeAbility:
    name = "search_knowledge"
    required_fields: List[str] = []

    def __init__(self) -> None:
        self._builder = RAGContextBuilder()

    async def execute(self, state: TaskState) -> TaskState:
        query = (
            str(state.external_data.get("query") or "").strip()
            or str(state.fields.get("I_nature_of_request") or "").strip()
            or "case"
        )
        payload: Dict[str, Any] = state.external_data or {}
        historical = payload.get("historical_docs") or []
        trees = payload.get("tree_docs") or []
        knowledge = payload.get("knowledge_docs") or []
        context = self._builder.build(query, state.fields, historical, trees, knowledge)
        state.external_data["knowledge_context"] = context
        return state
