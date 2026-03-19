from __future__ import annotations

from typing import Any, Dict, List

from agent.abilities.base import register_ability
from agent.task_state import TaskState
from services.llm_service import get_llm_service


@register_ability
class GenerateReplyAbility:
    name = "generate_reply"
    required_fields: List[str] = []

    async def execute(self, state: TaskState) -> TaskState:
        llm_service = get_llm_service()
        cfg: Dict[str, Any] = state.external_data or {}
        reply = llm_service.generate_reply_draft(
            reply_type=cfg.get("reply_type", "interim"),
            case_data=state.fields,
            template_content=cfg.get("template_content", ""),
            conversation_history=cfg.get("conversation_history", []),
            user_message=cfg.get("user_message"),
            language=cfg.get("language", "zh"),
            is_initial=bool(cfg.get("is_initial", False)),
            skip_questions=bool(cfg.get("skip_questions", False)),
        )
        if reply is not None:
            state.external_data["reply_result"] = reply
            state.external_data["reply_slip_selections"] = reply.get("reply_slip_selections", {})
            state.external_data["draft_text"] = reply.get("draft_reply") or reply.get("message", "")
            state.external_data["deadline"] = reply.get("deadline")
        return state
