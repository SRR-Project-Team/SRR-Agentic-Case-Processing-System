from __future__ import annotations

from typing import List

from agent.abilities.base import register_ability
from agent.task_state import TaskState
from services.llm_service import get_llm_service


@register_ability
class GenerateSummaryAbility:
    name = "generate_summary"
    required_fields: List[str] = []

    async def execute(self, state: TaskState) -> TaskState:
        try:
            llm_service = get_llm_service()
            source_text = (
                state.raw_content
                or str(state.fields.get("Q_case_details") or "")
                or str(state.fields)
            )
            override = (state.external_data or {}).get("summary_override") or {}
            negative_example = override.get("negative_example")
            summary = llm_service.summarize_text(
                source_text, negative_example=negative_example
            )
            if summary:
                state.summary = summary
                state.external_data["summary"] = summary
        except Exception:
            # Keep non-fatal fallback behavior for rollout safety.
            pass
        return state
