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
            override = (state.external_data or {}).get("summary_override") or {}
            negative_example = override.get("negative_example")
            summary_payload = llm_service.build_case_summary(
                state.fields,
                raw_text=state.raw_content or "",
                negative_example=negative_example,
            )
            summary = summary_payload.get("summary")
            if summary:
                state.summary = summary
                state.external_data["summary"] = summary
                state.external_data["summary_provenance"] = summary_payload.get("provenance")
        except Exception:
            # Keep non-fatal fallback behavior for rollout safety.
            pass
        return state
