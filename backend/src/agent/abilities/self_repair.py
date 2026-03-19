from __future__ import annotations

import copy
from typing import Any, Dict, List

from agent.abilities.base import register_ability
from agent.task_state import TaskState


@register_ability
class SelfRepairAbility:
    """Attempt targeted repair when quality is in the gray zone (0.3-0.5).

    Three repair strategies prioritized by failure type:
      coverage_low       -> re-summarize with stricter prompt
      extraction_incomplete -> re-run fill_missing
      faithfulness_low   -> flag for human review

    Each strategy runs at most once.  If quality doesn't improve,
    keep the original result (best-of-N = best-of-2).
    """

    name = "self_repair"
    required_fields: List[str] = []

    async def _run_candidate(self, state: TaskState, steps: List[str]) -> TaskState:
        from agent.abilities.base import run_ability

        candidate = copy.deepcopy(state)
        for step in steps:
            if step == "reset_summary":
                candidate.summary = ""
                continue
            candidate = await run_ability(step, candidate)
        return candidate

    def _select_strategy(
        self,
        state: TaskState,
        coverage: float,
        faithfulness: float,
        has_missing: bool,
    ) -> str:
        routing = (state.department_routing or {}) if hasattr(state, "department_routing") else {}
        conf = routing.get("confidence", "")
        conf_numeric = 0.8 if conf == "high" else (0.5 if conf == "medium" else 0.3)
        if conf_numeric < 0.7:
            return "routing_uncertain"
        if coverage < 0.4:
            return "coverage_low"
        if faithfulness < 0.4:
            return "faithfulness_low"
        if has_missing:
            return "extraction_incomplete"
        return "general_low_quality"

    async def execute(self, state: TaskState) -> TaskState:
        score = float(state.quality_score or 0.0)

        if score < 0.3 or score >= 0.5:
            return state

        if state.retry_record.get("self_repair", 0) >= 1:
            return state

        eval_data: Dict[str, Any] = state.external_data.get("quality_eval") or {}
        coverage = float(eval_data.get("answer_coverage", 1.0) or 1.0)
        faithfulness = float(eval_data.get("answer_faithfulness", 1.0) or 1.0)
        strategy = self._select_strategy(
            state, coverage, faithfulness, bool(state.missing_fields)
        )

        candidate_plans: List[Dict[str, Any]] = []
        if strategy == "routing_uncertain":
            candidate_plans = [
                {"name": "call_external_route", "steps": ["call_external", "route_department", "generate_summary", "eval_quality"]},
                {"name": "resummary_only", "steps": ["reset_summary", "generate_summary", "eval_quality"]},
            ]
        elif strategy == "coverage_low":
            state.external_data["search_override"] = {"strategy": "bm25_keyword"}
            candidate_plans = [
                {"name": "fill_then_resummary", "steps": ["search_similar_cases", "fill_missing", "generate_summary", "eval_quality"]},
                {"name": "resummary_only", "steps": ["reset_summary", "generate_summary", "eval_quality"]},
            ]
        elif strategy == "faithfulness_low":
            state.external_data["summary_override"] = {"negative_example": state.summary or ""}
            candidate_plans = [
                {"name": "resummary_only", "steps": ["reset_summary", "generate_summary", "eval_quality"]},
            ]
            state.external_data["repair_flag"] = "needs_human_review"
        elif strategy == "extraction_incomplete":
            state.external_data["extract_override"] = {"extractor": "llm_vision"}
            candidate_plans = [
                {"name": "fill_validate_summary", "steps": ["fill_missing", "check_completeness", "generate_summary", "eval_quality"]},
                {"name": "fill_only_eval", "steps": ["fill_missing", "eval_quality"]},
            ]
        else:
            candidate_plans = [
                {"name": "resummary_only", "steps": ["reset_summary", "generate_summary", "eval_quality"]},
            ]

        best_state = state
        best_score = score
        explored: List[Dict[str, Any]] = []
        for plan in candidate_plans:
            try:
                candidate = await self._run_candidate(state, plan["steps"])
                cand_score = float(candidate.quality_score or 0.0)
                explored.append(
                    {
                        "name": plan["name"],
                        "steps": plan["steps"],
                        "quality_score": cand_score,
                    }
                )
                if cand_score > best_score:
                    best_state = candidate
                    best_score = cand_score
            except Exception as exc:
                explored.append(
                    {
                        "name": plan["name"],
                        "steps": plan["steps"],
                        "error": str(exc),
                    }
                )

        improved = (best_score - score) >= 0.03
        output_state = best_state if improved else state
        output_state.external_data["self_repair"] = {
            "triggered": True,
            "action": strategy,
            "pre_score": score,
            "post_score": float(output_state.quality_score or score),
            "improved": improved,
            "best_of_n": len(candidate_plans),
            "candidates": explored,
        }
        output_state.external_data["self_repair_best_candidate"] = (
            max(explored, key=lambda item: float(item.get("quality_score", -1.0)), default={})
        )
        output_state.external_data["self_repair_selected"] = "best_candidate" if improved else "original"
        output_state.quality_score = float(output_state.quality_score or score)
        output_state.increase_retry("self_repair")
        return output_state
