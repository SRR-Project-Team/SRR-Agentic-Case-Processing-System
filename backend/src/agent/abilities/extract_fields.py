from __future__ import annotations

import os
from typing import Dict, List

from agent.abilities.base import register_ability
from agent.task_state import TaskState
from core.extractFromRCC import extract_case_data_from_pdf as extract_rcc_from_pdf
from core.extractFromTMO import extract_case_data_from_pdf as extract_tmo_from_pdf
from core.extractFromTxt import extract_case_data, extract_case_data_from_txt
from services.user_feedback_service import UserFeedbackService
from utils.file_utils import read_file_with_encoding


CORE_FIELDS: List[str] = [
    "A_date_received",
    "B_source",
    "C_case_number",
    "G_slope_no",
    "H_location",
    "I_nature_of_request",
    "J_subject_matter",
]


@register_ability
class ExtractFieldsAbility:
    name = "extract_fields"
    required_fields: List[str] = []

    async def execute(self, state: TaskState) -> TaskState:
        source = (state.source_type or "").upper()
        extracted: Dict[str, object] = {}

        correction_hints: List[Dict[str, str]] = []
        try:
            svc = UserFeedbackService()
            query = (
                (state.raw_content or "")[:2000]
                or str(state.fields or {})[:1000]
                or "case extraction"
            )
            feedback_rows = await svc.retrieve_feedback(query, top_k=5)
            for r in feedback_rows:
                parsed = UserFeedbackService.parse_feedback_rule(r.get("content") or "")
                if parsed:
                    correction_hints.append(parsed)
        except Exception:
            pass

        few_shot_cases: List[Dict] = []
        try:
            raw_for_search = state.raw_content or ""
            if not raw_for_search and state.file_path and os.path.isfile(state.file_path):
                raw_for_search = read_file_with_encoding(state.file_path) or ""
            raw_for_search = (raw_for_search or "")[:2000]
            if raw_for_search:
                from services.hybrid_search_service import (
                    get_hybrid_search_service,
                    init_hybrid_search_service,
                )
                from services.historical_case_matcher import get_historical_matcher
                from src.core.pg_vector_store import PgVectorStore

                try:
                    hybrid = get_hybrid_search_service()
                except RuntimeError:
                    matcher = get_historical_matcher()
                    vector_client = PgVectorStore()
                    init_hybrid_search_service(vector_client, matcher)
                    hybrid = get_hybrid_search_service()
                few_shot_cases = await hybrid.find_similar_by_raw_content(
                    raw_for_search, limit=5
                )
        except Exception:
            pass

        if source == "ICC":
            if state.file_path:
                extracted = extract_case_data_from_txt(
                    state.file_path,
                    correction_hints=correction_hints,
                    few_shot_cases=few_shot_cases,
                ) or {}
            elif state.raw_content:
                extracted = extract_case_data(
                    state.raw_content,
                    original_content=state.raw_content,
                    file_path=state.file_path or None,
                ) or {}
        elif source == "TMO":
            if state.file_path:
                extracted = extract_tmo_from_pdf(state.file_path) or {}
        elif source == "RCC":
            if state.file_path:
                extracted = extract_rcc_from_pdf(state.file_path) or {}

        extract_override = (state.external_data or {}).get("extract_override") or {}
        if extract_override.get("extractor") == "llm_vision":
            attachments = (state.external_data or {}).get("attachments") or {}
            try:
                for item in (attachments.get("location_plans") or [])[:3]:
                    data = (item.get("extracted") or item.get("parsed")) if isinstance(item, dict) else {}
                    if data.get("slope_no") and not extracted.get("G_slope_no"):
                        extracted["G_slope_no"] = data["slope_no"]
                    if data.get("area") or data.get("road"):
                        loc = " ".join(filter(None, [data.get("area"), data.get("road")]))
                        if loc and not extracted.get("H_location"):
                            extracted["H_location"] = loc
                for item in (attachments.get("site_photos") or [])[:2]:
                    data = (item.get("extracted") or item.get("parsed")) if isinstance(item, dict) else {}
                    if data.get("description") and not extracted.get("Q_case_details"):
                        extracted["Q_case_details"] = (extracted.get("Q_case_details") or "") + "\n" + data["description"]
            except Exception:
                pass

        if extracted:
            state.fields.update(extracted)

        state.missing_fields = [
            key for key in CORE_FIELDS if state.fields.get(key) in (None, "", [], {})
        ]
        return state
