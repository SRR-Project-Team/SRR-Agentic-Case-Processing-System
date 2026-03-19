from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Dict, List

from agent.abilities.base import register_ability
from agent.task_state import TaskState
from agent.evaluators import evaluate_with_funnel


def _normalize_eval_payload(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict):
        return value
    if hasattr(value, "__dict__"):
        return dict(value.__dict__)
    return {}


@register_ability
class EvaluateQualityAbility:
    name = "eval_quality"
    required_fields: List[str] = []

    async def execute(self, state: TaskState) -> TaskState:
        payload = state.external_data or {}
        try:
            ragas_enabled = bool(payload.get("ragas_enabled", False))

            query = str(payload.get("query") or state.fields.get("I_nature_of_request") or "")
            answer = str(payload.get("answer") or state.summary or "")
            contexts_raw = payload.get("contexts") or []
            if isinstance(contexts_raw, list):
                contexts = "\n\n".join(str(c) for c in contexts_raw if c is not None)
            else:
                contexts = str(contexts_raw or "")
            retrieval_metrics = payload.get("retrieval_metrics") or []

            result = evaluate_with_funnel(
                query=query,
                answer=answer,
                contexts=contexts,
                fields=state.fields,
                retrieval_metrics=retrieval_metrics,
                ragas_enabled=ragas_enabled,
            )
            eval_data = _normalize_eval_payload(result)
            if eval_data:
                score = float(eval_data.get("quality_score", 0.0) or 0.0)
                state.quality_score = score
                state.external_data["quality_eval"] = eval_data
        except Exception:
            state.quality_score = float(state.quality_score or 0.0)
        return state
