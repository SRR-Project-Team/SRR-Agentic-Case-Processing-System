from __future__ import annotations

from typing import Any, Dict, List

from agent.abilities.base import register_ability
from agent.task_state import TaskState
from services.user_feedback_service import UserFeedbackService


@register_ability
class UserFeedbackAbility:
    """Inject previously approved user corrections into current case state."""

    name = "user_feedback"
    required_fields: List[str] = []

    def __init__(self) -> None:
        self._service = UserFeedbackService()

    def _query_from_state(self, state: TaskState) -> str:
        pieces = [
            str((state.fields or {}).get("I_nature_of_request") or ""),
            str((state.fields or {}).get("Q_case_details") or ""),
            str((state.fields or {}).get("J_subject_matter") or ""),
            str(state.raw_content or "")[:1200],
        ]
        query = " ".join(p.strip() for p in pieces if p and p.strip())
        return query or "case feedback"

    async def execute(self, state: TaskState) -> TaskState:
        query = self._query_from_state(state)
        feedback_docs = await self._service.retrieve_feedback(query, top_k=5, min_similarity=0.25)
        if not feedback_docs:
            return state

        payload: Dict[str, Any] = dict(state.external_data or {})
        payload["user_feedback_docs"] = feedback_docs

        applied: List[Dict[str, str]] = []
        constraints: List[str] = []
        for doc in feedback_docs:
            rule = UserFeedbackService.parse_feedback_rule(str(doc.get("content") or ""))
            if not rule:
                continue

            field_name = (rule.get("field") or "").strip()
            if not field_name:
                continue
            constraints.append(
                f"{field_name}: prefer '{rule.get('correct', '')}' over '{rule.get('incorrect', '')}'"
            )
            current = str((state.fields or {}).get(field_name) or "").strip()
            incorrect = (rule.get("incorrect") or "").strip()
            correct = (rule.get("correct") or "").strip()

            if not correct:
                continue
            if not current or (incorrect and current.lower() == incorrect.lower()):
                state.fields[field_name] = correct
                if field_name in state.missing_fields:
                    state.missing_fields.remove(field_name)
                applied.append({"field": field_name, "from": current, "to": correct})

        if constraints:
            payload["user_feedback_constraints"] = constraints
        if applied:
            payload["user_feedback_applied"] = applied
        state.external_data = payload
        return state

