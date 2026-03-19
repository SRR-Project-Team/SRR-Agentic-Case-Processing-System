from __future__ import annotations

from typing import List

from agent.abilities.base import register_ability
from agent.task_state import TaskState


@register_ability
class ChatAnswerAbility:
    """
    Bridge ability for chat streaming.

    The actual streaming orchestration remains in agent.graph.stream_chat_events.
    This ability records that chat answer generation is requested so process_case()
    can keep a unified steps pipeline.
    """

    name = "chat_answer"
    required_fields: List[str] = []

    async def execute(self, state: TaskState) -> TaskState:
        state.external_data["chat_answer_requested"] = True
        return state
