"""
RAG Evaluation Strategies.

Two pluggable evaluators that share the same interface:
  - KeywordEvaluator  : fast, zero-cost, keyword-overlap heuristic (original)
  - RagasEvaluator    : LLM-as-Judge via RAGAS framework (upgrade)

Both return a dict with the same keys so _finalize_rag_eval() is agnostic
to the underlying scoring engine.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_MAX_KEYWORDS_DISPLAY = 20


# ── helpers ─────────────────────────────────────────────────────────

_SYNONYM_MAP = {
    "tree": {"樹", "樹木", "树", "树木"},
    "inventory": {"清單", "清单", "列表"},
    "slope": {"斜坡", "坡"},
    "case": {"個案", "个案"},
    "inspection": {"檢查", "检查"},
    "report": {"報告", "报告"},
    "record": {"記錄", "记录"},
    "detail": {"詳情", "详情"},
    "data": {"資料", "资料", "數據", "数据"},
}


def _expand_with_synonyms(terms: set) -> set:
    expanded = set(terms)
    for base, synonyms in _SYNONYM_MAP.items():
        all_forms = synonyms | {base}
        if expanded & all_forms:
            expanded |= all_forms
    return expanded


def _tokenize(text: str) -> set:
    tokens = set(re.findall(r"[\w\u4e00-\u9fff]{2,}", (text or "").lower()))
    # CJK bigrams for unsegmented Chinese (no spaces between words)
    for run in re.findall(r"[\u4e00-\u9fff]+", (text or "")):
        for i in range(len(run) - 1):
            tokens.add(run[i : i + 2])
    return tokens


def _keyword_overlap(reference: str, text: str) -> float:
    """Relevance proxy with cross-lingual synonym expansion and CJK bigrams."""
    ref_terms = _tokenize(reference)
    txt_terms = _tokenize(text)
    if not ref_terms:
        return 0.0
    ref_expanded = _expand_with_synonyms(ref_terms)
    txt_expanded = _expand_with_synonyms(txt_terms)
    return len(ref_expanded & txt_expanded) / max(len(ref_expanded), 1)


def _keyword_overlap_detailed(
    reference: str, text: str
) -> Tuple[float, List[str], List[str]]:
    """
    Returns (ratio, matched_terms, missed_terms).
    matched = ref ∩ text, missed = ref - text.
    Terms sorted by length (longer first), capped at _MAX_KEYWORDS_DISPLAY.
    """
    ref_terms = _tokenize(reference)
    txt_terms = _tokenize(text)
    ref_expanded = _expand_with_synonyms(ref_terms)
    txt_expanded = _expand_with_synonyms(txt_terms)
    matched = ref_expanded & txt_expanded
    missed = ref_expanded - txt_expanded
    ratio = len(matched) / max(len(ref_expanded), 1)
    matched_list = sorted(matched, key=lambda x: -len(x))[:_MAX_KEYWORDS_DISPLAY]
    missed_list = sorted(missed, key=lambda x: -len(x))[:_MAX_KEYWORDS_DISPLAY]
    return ratio, matched_list, missed_list


def _avg(values: List[float]) -> float:
    return sum(values) / len(values) if values else 0.0


# ── Result container ────────────────────────────────────────────────

@dataclass
class EvalResult:
    """Unified evaluation result."""
    context_relevance: float
    answer_faithfulness: float
    answer_coverage: float
    quality_score: float
    eval_method: str  # "keyword_overlap" | "ragas"
    faithfulness_matched: List[str] = field(default_factory=list)
    faithfulness_total: int = 0
    coverage_matched: List[str] = field(default_factory=list)
    coverage_missed: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "context_relevance": round(self.context_relevance, 4),
            "answer_faithfulness": round(self.answer_faithfulness, 4),
            "answer_coverage": round(self.answer_coverage, 4),
            "quality_score": round(self.quality_score, 4),
            "eval_method": self.eval_method,
            "faithfulness_matched": self.faithfulness_matched,
            "faithfulness_total": self.faithfulness_total,
            "coverage_matched": self.coverage_matched,
            "coverage_missed": self.coverage_missed,
        }


# ── Strategy 1: Keyword Overlap (original) ─────────────────────────

class KeywordEvaluator:
    """Original keyword-overlap heuristic — zero latency, no API cost."""

    def score(
        self,
        query: str,
        answer: str,
        contexts: str,
        retrieval_metrics: Optional[List[Dict[str, Any]]] = None,
    ) -> EvalResult:
        metrics = retrieval_metrics or []

        # Mark which docs were used
        for m in metrics:
            snippet = m.get("snippet", "")
            m["used_in_answer"] = _keyword_overlap(answer, snippet) >= 0.10

        context_relevance = _avg(
            [float(m.get("relevance_score", 0.0) or 0.0) for m in metrics]
        )

        if contexts:
            faith_ratio, faith_matched, _ = _keyword_overlap_detailed(answer, contexts)
            answer_faithfulness = min(1.0, 0.2 + 0.8 * faith_ratio)
            ref_terms = _tokenize(answer)
            ref_expanded = _expand_with_synonyms(ref_terms)
            faithfulness_total = len(ref_expanded)
        else:
            answer_faithfulness = 0.0
            faith_matched = []
            faithfulness_total = 0

        cov_ratio, cov_matched, cov_missed = _keyword_overlap_detailed(query, answer)
        answer_coverage = min(1.0, cov_ratio * 1.15)

        quality_score = (
            context_relevance * 0.30
            + answer_faithfulness * 0.40
            + answer_coverage * 0.30
        )
        return EvalResult(
            context_relevance=context_relevance,
            answer_faithfulness=answer_faithfulness,
            answer_coverage=answer_coverage,
            quality_score=quality_score,
            eval_method="keyword_overlap",
            faithfulness_matched=faith_matched,
            faithfulness_total=faithfulness_total,
            coverage_matched=cov_matched,
            coverage_missed=cov_missed,
        )


# ── Strategy 2: RAGAS LLM-as-Judge ─────────────────────────────────

class RagasEvaluator:
    """
    RAGAS-based evaluation using LLM-as-Judge.

    Metrics mapping to existing fields:
      context_relevance  → ragas ContextRelevancy
      answer_faithfulness → ragas Faithfulness
      answer_coverage    → ragas AnswerRelevancy (closest semantic equivalent)

    Uses asyncio.wait_for with configurable timeout.  Falls back to
    KeywordEvaluator on any failure.
    """

    def __init__(self, timeout_seconds: int = 8, model: str = "gpt-4o"):
        self._timeout = timeout_seconds
        self._model = model
        self._fallback = KeywordEvaluator()

    async def score(
        self,
        query: str,
        answer: str,
        contexts: str,
        retrieval_metrics: Optional[List[Dict[str, Any]]] = None,
    ) -> EvalResult:
        try:
            result = await asyncio.wait_for(
                self._run_ragas(query, answer, contexts),
                timeout=self._timeout,
            )
            # still mark used_in_answer for UI compatibility
            for m in (retrieval_metrics or []):
                snippet = m.get("snippet", "")
                m["used_in_answer"] = _keyword_overlap(answer, snippet) >= 0.10
            return result
        except asyncio.TimeoutError:
            logger.warning(
                "RAGAS evaluation timed out after %ds, falling back to keyword overlap",
                self._timeout,
            )
        except Exception as e:
            logger.warning("RAGAS evaluation failed (%s), falling back to keyword overlap", e)

        return self._fallback.score(query, answer, contexts, retrieval_metrics)

    async def _run_ragas(self, query: str, answer: str, contexts: str) -> EvalResult:
        """Execute RAGAS evaluation in a thread pool to avoid blocking the event loop."""
        return await asyncio.to_thread(self._evaluate_sync, query, answer, contexts)

    def _evaluate_sync(self, query: str, answer: str, contexts: str) -> EvalResult:
        """Synchronous RAGAS evaluation — runs inside a thread."""
        # Lazy import so the module can load even without ragas installed
        from ragas import evaluate as ragas_evaluate
        from ragas.metrics import (
            context_relevancy,
            faithfulness,
            answer_relevancy,
        )
        from datasets import Dataset
        from langchain_openai import ChatOpenAI
        from ragas.llms import LangchainLLMWrapper
        import os

        # Split contexts into list (RAGAS expects List[str] per sample)
        context_list = [
            block.strip()
            for block in contexts.split("\n\n")
            if block.strip()
        ] or [""]

        dataset = Dataset.from_dict({
            "question": [query],
            "answer": [answer],
            "contexts": [context_list],
        })

        evaluator_llm = LangchainLLMWrapper(
            ChatOpenAI(
                model=self._model,
                api_key=os.getenv("OPENAI_API_KEY"),
                temperature=0,
            )
        )

        results = ragas_evaluate(
            dataset=dataset,
            metrics=[context_relevancy, faithfulness, answer_relevancy],
            llm=evaluator_llm,
        )

        # Extract scores (RAGAS returns 0–1 floats)
        ctx_rel = float(results.get("context_relevancy", 0.0) or 0.0)
        faith = float(results.get("faithfulness", 0.0) or 0.0)
        coverage = float(results.get("answer_relevancy", 0.0) or 0.0)

        quality_score = ctx_rel * 0.30 + faith * 0.40 + coverage * 0.30

        return EvalResult(
            context_relevance=ctx_rel,
            answer_faithfulness=faith,
            answer_coverage=coverage,
            quality_score=quality_score,
            eval_method="ragas",
        )


# ── Strategy 2.5: Rule Validator (L2 gate) ─────────────────────────

_SLOPE_FMT = re.compile(r"^\d{1,2}[A-Za-z]{2,3}[-/][A-Za-z0-9/()\-]+$")
_DATE_FMT = re.compile(r"^\d{1,2}-[A-Za-z]{3}-\d{4}$")
_D_TYPES = {"Emergency", "Urgent", "General"}

_L2_REQUIRED = [
    "A_date_received", "B_source", "C_case_number",
    "G_slope_no", "H_location", "I_nature_of_request", "J_subject_matter",
]


class RuleValidator:
    """L2 structured-rule check between keyword heuristic and RAGAS.

    Scoring funnel:
      L1 < 0.3  -> fail immediately
      L1 >= 0.5 -> pass immediately
      0.3 ~ 0.5 -> enter L2 rule validation
        L2 fail -> quality capped at 0.29
        L2 pass -> proceed to L3 (RAGAS) or accept L1 score
    """

    def validate(self, fields: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Return (passed, violations)."""
        violations: List[str] = []

        filled = sum(1 for k in _L2_REQUIRED if fields.get(k) not in (None, "", [], {}))
        fill_rate = filled / len(_L2_REQUIRED) if _L2_REQUIRED else 0.0
        if fill_rate < 0.5:
            violations.append(f"field_fill_rate={fill_rate:.0%} < 50%")

        slope = str(fields.get("G_slope_no") or "").strip()
        if slope and not _SLOPE_FMT.match(slope):
            violations.append(f"G_slope_no format invalid: {slope}")

        a_date = str(fields.get("A_date_received") or "").strip()
        if a_date and not _DATE_FMT.match(a_date):
            violations.append(f"A_date_received not dd-MMM-yyyy: {a_date}")

        d_type = str(fields.get("D_type") or "").strip()
        if d_type and d_type not in _D_TYPES:
            violations.append(f"D_type '{d_type}' invalid")

        return (len(violations) == 0), violations


_rule_validator = RuleValidator()


# ── Factory ─────────────────────────────────────────────────────────

_keyword_evaluator = KeywordEvaluator()
_ragas_evaluator: Optional[RagasEvaluator] = None


def get_evaluator(ragas_enabled: bool = False, **kwargs) -> KeywordEvaluator | RagasEvaluator:
    """Return the appropriate evaluator based on feature flag."""
    if not ragas_enabled:
        return _keyword_evaluator
    global _ragas_evaluator
    if _ragas_evaluator is None:
        _ragas_evaluator = RagasEvaluator(**kwargs)
    return _ragas_evaluator


def get_rule_validator() -> RuleValidator:
    return _rule_validator


def evaluate_with_funnel(
    query: str,
    answer: str,
    contexts: str,
    fields: Dict[str, Any],
    retrieval_metrics: Optional[List[Dict[str, Any]]] = None,
    ragas_enabled: bool = False,
) -> EvalResult:
    """Three-layer evaluation funnel: L1 keyword -> L2 rules -> L3 RAGAS."""
    l1_result = _keyword_evaluator.score(query, answer, contexts, retrieval_metrics)
    l1_score = l1_result.quality_score

    if l1_score < 0.3:
        l1_result.eval_method = "keyword_overlap|L1_fail"
        return l1_result

    if l1_score >= 0.5:
        l1_result.eval_method = "keyword_overlap|L1_pass"
        return l1_result

    l2_pass, violations = _rule_validator.validate(fields)
    if not l2_pass:
        l1_result.quality_score = min(l1_result.quality_score, 0.29)
        l1_result.eval_method = f"keyword_overlap|L2_fail({len(violations)})"
        return l1_result

    if not ragas_enabled:
        l1_result.eval_method = "keyword_overlap|L2_pass"
        return l1_result

    evaluator = get_evaluator(ragas_enabled=True)
    try:
        import asyncio
        loop = asyncio.get_event_loop()
        if loop.is_running():
            l1_result.eval_method = "keyword_overlap|L2_pass_ragas_skipped"
            return l1_result
        l3_result = loop.run_until_complete(
            evaluator.score(query, answer, contexts, retrieval_metrics)
        )
        l3_result.eval_method = "ragas|L3"
        return l3_result
    except Exception:
        l1_result.eval_method = "keyword_overlap|L3_fallback"
        return l1_result
