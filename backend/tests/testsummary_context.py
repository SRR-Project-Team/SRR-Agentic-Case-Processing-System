import logging
import os
import sys

_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_SRC_DIR = os.path.join(_BACKEND_DIR, "src")
for _p in (_BACKEND_DIR, _SRC_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from services.llm_service import LLMService
from services.summary_context import (
    assemble_summary_context,
    build_deterministic_summary,
    summary_has_role_confusion,
)


ICC_RAW_TEXT = """
1823 CASE: 3-9400481748
II. ASSIGNMENT HISTORY:
--------------------------
[Date/Time]      [Status]    [Dept]   [Assigned To]
2026-04-15 16:36:28    Open        ASD    Property Services Branch
"""


def _build_service_without_llm() -> LLMService:
    svc = LLMService(api_key="", provider="openai")
    svc.logger = logging.getLogger("test-summary")
    return svc


def test_assemble_summary_context_extracts_icc_handling_department() -> None:
    ctx = assemble_summary_context(
        {
            "A_date_received": "15-Apr-2026",
            "B_source": "ICC",
            "D_type": "Urgent",
            "E_caller_name": "謝",
            "H_location": "北社新村",
            "I_nature_of_request": "tree issue on slope",
            "J_subject_matter": "Others",
        },
        raw_text=ICC_RAW_TEXT,
    )

    assert ctx["source_channel"] == "ICC / 1823 public channel"
    assert ctx["handling_department"] == "Property Services Branch"
    assert ctx["caller_name"] == "謝"


def test_build_case_summary_uses_structured_context_not_bad_candidate() -> None:
    svc = _build_service_without_llm()

    payload = svc.build_case_summary(
        {
            "A_date_received": "15-Apr-2026",
            "B_source": "ICC",
            "D_type": "Urgent",
            "E_caller_name": "謝",
            "H_location": "北社新村",
            "I_nature_of_request": "tree issue on slope",
            "J_subject_matter": "Others",
        },
        raw_text=ICC_RAW_TEXT,
        candidate_summary='On April 15, 2026, a case was filed by caller 謝 from the Property Services Branch.',
    )

    summary = payload["summary"]
    assert payload["provenance"] == "structured_summary_deterministic"
    assert "Property Services Branch" in summary
    assert "assigned to Property Services Branch" in summary
    assert "caller 謝 from the Property Services Branch" not in summary
    assert "from the Property Services Branch" not in summary


def test_review_sum_repairs_icc_role_confusion_without_llm() -> None:
    svc = _build_service_without_llm()

    reviewed = svc._review_sum_(
        "On April 15, 2026, a service request was filed by caller 謝 from the Property Services Branch regarding a tree issue.",
        {
            "A_date_received": "15-Apr-2026",
            "B_source": "ICC",
            "D_type": "Urgent",
            "E_caller_name": "謝",
            "H_location": "北社新村",
            "I_nature_of_request": "tree issue on slope",
            "J_subject_matter": "Others",
        },
    )

    assert reviewed
    assert "assigned to Property Services Branch" not in reviewed
    assert "Property Services Branch" not in reviewed
    assert "caller 謝 from the Property Services Branch" not in reviewed


def test_summary_has_role_confusion_flags_bad_icc_phrase() -> None:
    ctx = assemble_summary_context(
        {
            "B_source": "ICC",
            "E_caller_name": "謝",
        },
        raw_text=ICC_RAW_TEXT,
    )

    assert summary_has_role_confusion(
        "The case was filed by caller 謝 from the Property Services Branch.",
        ctx,
    ) is True
    assert summary_has_role_confusion(
        build_deterministic_summary(ctx),
        ctx,
    ) is False


def test_raw_summary_prompt_uses_source_channel_not_caller_department() -> None:
    svc = _build_service_without_llm()

    prompt = svc._build_raw_summary_prompt("Sample log text.")

    assert "source channel" in prompt
    assert "handling / assigned department if explicit and relevant" in prompt
    assert "3) caller department" not in prompt
