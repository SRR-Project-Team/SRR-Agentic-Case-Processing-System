import asyncio
import json
import logging
import queue
import time
from typing import Any, AsyncGenerator, Dict, List, Optional

from .nodes import (
    classify_intent,
    decomposition_metadata,
    decompose_question,
    should_retrieve_context,
)
from . import abilities as _ability_registry_bootstrap
from .abilities import run_ability
from .evaluators import KeywordEvaluator, RagasEvaluator, get_evaluator
from .state import AgentState, RetrievalMetric, RAGEvaluation, ThinkingStep
from .task_state import TaskState
from .tools import AgentTooling

logger = logging.getLogger(__name__)
from services.context_manager import ContextManager
from services.session_state_service import SessionStateService

# Keep import side effects so abilities are registered before orchestration.
_ = _ability_registry_bootstrap


def _avg(values: List[float]) -> float:
    return sum(values) / len(values) if values else 0.0


async def process_case(state: TaskState) -> TaskState:
    """Condition-driven create_case orchestration using atomic abilities."""
    if state.case_id and (not state.fields or len(state.fields) < 5):
        try:
            from database.manager import get_db_manager
            db = get_db_manager()
            case_row = db.get_case(state.case_id)
            if case_row:
                field_map = {
                    "A_date_received",
                    "B_source",
                    "C_case_number",
                    "D_type",
                    "E_caller_name",
                    "F_contact_no",
                    "G_slope_no",
                    "H_location",
                    "I_nature_of_request",
                    "J_subject_matter",
                    "K_10day_rule_due_date",
                    "L_icc_interim_due",
                    "M_icc_final_due",
                    "N_works_completion_due",
                    "O1_fax_to_contractor",
                    "O2_email_send_time",
                    "P_fax_pages",
                    "Q_case_details",
                }
                for key in field_map:
                    val = case_row.get(key)
                    if val is not None and val != "" and state.fields.get(key) in (None, "", []):
                        state.fields[key] = val
                state.external_data["case_loaded_from_db"] = True
        except Exception:
            pass

    if state.fields:
        state.mark_step_done("extract_fields")
    else:
        state = await run_ability("extract_fields", state)

    state = await run_ability("user_feedback", state)

    if state.missing_fields:
        state = await run_ability("fill_missing", state)
    state = await run_ability("check_completeness", state)

    if (state.source_type or "").upper() == "ICC":
        # Let ability decide if referral history exists; always invoke for ICC.
        state = await run_ability("annotate_referral", state)

    state = await run_ability("call_external", state)

    slope_candidates = list((state.external_data or {}).get("slope_candidates") or [])
    if len(slope_candidates) > 1:
        try:
            from services.slope_service import SlopeService

            slope_service = SlopeService()
            multi = await slope_service.check_multi_department(slope_candidates)
            state.external_data["multi_slope_analysis"] = multi
            if multi.get("split_needed"):
                sub_tasks: List[Dict[str, Any]] = []
                for idx, slope in enumerate(slope_candidates, start=1):
                    dept = await slope_service.determine_department(slope)
                    sub_tasks.append(
                        {
                            "sub_task_id": f"{state.task_id}-S{idx}",
                            "slope_no": slope,
                            "department_routing": dept,
                            "status": "planned",
                        }
                    )
                state.external_data["sub_tasks"] = sub_tasks
                state.department_routing = {
                    "department": "MULTI",
                    "confidence": "medium",
                    "source": "multi_slope_split",
                    "split_needed": True,
                    "sub_tasks": sub_tasks,
                }
                state.mark_step_done("split_multi_slope")
        except Exception as exc:
            state.add_error(f"split_multi_slope: {exc}")

    if state.similar_cases:
        state.mark_step_done("search_similar_cases")
    else:
        state = await run_ability("search_similar_cases", state)
    if (state.source_type or "").upper() == "ICC":
        state = await run_ability("detect_duplicate", state)

    split_needed = bool(((state.external_data or {}).get("multi_slope_analysis") or {}).get("split_needed"))
    if state.fields.get("G_slope_no") and not split_needed:
        state = await run_ability("route_department", state)
    state = await run_ability("calculate_deadlines", state)

    if state.summary:
        state.mark_step_done("generate_summary")
    else:
        state = await run_ability("generate_summary", state)
    state = await run_ability("eval_quality", state)
    if 0.3 <= float(state.quality_score or 0.0) < 0.5:
        state = await run_ability("self_repair", state)

    return state


def _append_step(
    state: AgentState,
    *,
    title: str,
    content: str,
    step_type: str,
    start_at: Optional[float] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> ThinkingStep:
    steps = state.setdefault("thinking_steps", [])
    duration_ms = int((time.perf_counter() - start_at) * 1000) if start_at else 0
    step: ThinkingStep = {
        "step_id": len(steps) + 1,
        "title": title,
        "content": content,
        "step_type": step_type,  # type: ignore[assignment]
        "duration_ms": duration_ms,
        "metadata": metadata or {},
    }
    steps.append(step)
    return step


def _extract_retrieval_metrics_from_text(query: str, his_context: str) -> List[RetrievalMetric]:
    """Fallback: parse retrieval metrics from plain-text context (legacy path).

    Prefer using structured metrics returned by build_context() instead.
    """
    import re as _re

    def _kw_overlap(ref: str, txt: str) -> float:
        ref_t = set(_re.findall(r"[\w\u4e00-\u9fff]{2,}", (ref or "").lower()))
        txt_t = set(_re.findall(r"[\w\u4e00-\u9fff]{2,}", (txt or "").lower()))
        return len(ref_t & txt_t) / max(len(ref_t), 1) if ref_t else 0.0

    source = ""
    counters: Dict[str, int] = {"historical_cases": 0, "tree_inventory": 0, "knowledge_base": 0, "other": 0}
    metrics: List[RetrievalMetric] = []

    for raw_line in (his_context or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lower = line.lower()
        if "relevant historical cases" in lower or lower.startswith("historical cases:"):
            source = "historical_cases"
            continue
        if "tree inventory" in lower:
            source = "tree_inventory"
            continue
        if "reference knowledge" in lower or lower.startswith("knowledge base docs:"):
            source = "knowledge_base"
            continue
        if lower.startswith("recent conversation context"):
            source = "other"
            continue

        if source == "":
            continue

        normalized = line.lstrip("- ").strip()
        if not normalized:
            continue
        counters[source] = counters.get(source, 0) + 1
        overlap = _kw_overlap(query, normalized)
        metrics.append(
            {
                "source": source,
                "doc_id": f"{source}-{counters[source]}",
                "doc_title": normalized[:80],
                "similarity_score": round(max(overlap, 0.05), 4),
                "relevance_score": round(max(overlap, 0.05), 4),
                "used_in_answer": False,
                "snippet": normalized[:320],
            }
        )
    return metrics


def _with_reasoning_scaffold(his_context: str) -> str:
    reasoning_instructions = (
        "Reasoning framework for assistant (do not expose internal reasoning in output):\n"
        "1) Understand the user intent and identify required facts.\n"
        "2) Prioritize factual evidence from Raw Content and retrieved context.\n"
        "3) Cross-check conflicting evidence and prefer explicit records.\n"
        "4) Produce a concise final answer, and state uncertainty when evidence is insufficient."
    )
    if his_context:
        return f"{his_context}\n\n{reasoning_instructions}"
    return reasoning_instructions


def _finalize_rag_eval(state: AgentState, answer_text: str) -> RAGEvaluation:
    """Compute quality scores using KeywordEvaluator (synchronous, fast)."""
    rag_eval = state.setdefault("rag_evaluation", {})
    metrics = rag_eval.get("retrieval_metrics", []) or []
    his_context = state.get("his_context", "")
    query = state.get("query", "")

    evaluator = KeywordEvaluator()
    result = evaluator.score(query, answer_text, his_context, metrics)

    used_count = sum(1 for m in metrics if m.get("used_in_answer"))
    rag_eval.update(result.to_dict())
    rag_eval["total_docs_retrieved"] = len(metrics)
    rag_eval["total_docs_used"] = used_count
    return rag_eval


async def _finalize_rag_eval_async(state: AgentState, answer_text: str) -> RAGEvaluation:
    """Compute quality scores using RAGAS LLM-as-Judge (async, higher accuracy)."""
    from config.settings import RAGAS_TIMEOUT_SECONDS, RAGAS_LLM_MODEL

    rag_eval = state.setdefault("rag_evaluation", {})
    metrics = rag_eval.get("retrieval_metrics", []) or []
    his_context = state.get("his_context", "")
    query = state.get("query", "")

    evaluator = get_evaluator(
        ragas_enabled=True,
        timeout_seconds=RAGAS_TIMEOUT_SECONDS,
        model=RAGAS_LLM_MODEL,
    )
    result = await evaluator.score(query, answer_text, his_context, metrics)

    used_count = sum(1 for m in metrics if m.get("used_in_answer"))
    rag_eval.update(result.to_dict())
    rag_eval["total_docs_retrieved"] = len(metrics)
    rag_eval["total_docs_used"] = used_count
    logger.info("RAG eval completed [method=%s, quality=%.2f]", result.eval_method, result.quality_score)
    return rag_eval


def _check_quality_alert(state: AgentState, rag_eval: RAGEvaluation) -> None:
    """Log quality/latency alerts for observability. Best-effort, must not raise."""
    try:
        from services.adaptive_rag_config import get_adaptive_rag_config

        config = get_adaptive_rag_config()
        quality = float(rag_eval.get("quality_score") or 0)
        latency = int(rag_eval.get("total_latency_ms") or 0)

        if quality < config.quality_alert_floor:
            logger.warning(
                "LOW_QUALITY_ALERT session=%s quality=%.2f intent=%s query=%s",
                state.get("session_id"),
                quality,
                state.get("intent"),
                (state.get("query") or "")[:80],
            )

        if latency > config.latency_alert_ms:
            logger.warning(
                "HIGH_LATENCY_ALERT session=%s latency=%dms docs=%d",
                state.get("session_id"),
                latency,
                rag_eval.get("total_docs_retrieved", 0),
            )
    except Exception:
        pass


def _persist_quality_metrics(
    state: AgentState,
    response_text: str,
    stream_error: str,
) -> None:
    session_id = state.get("session_id")
    if not session_id:
        return
    try:
        from database.manager import get_db_manager

        db_manager = get_db_manager()
        user_phone = None
        if hasattr(db_manager, "get_session_owner_phone"):
            user_phone = db_manager.get_session_owner_phone(session_id)
        if hasattr(db_manager, "save_chat_quality_metric"):
            db_manager.save_chat_quality_metric(
                {
                    "session_id": session_id,
                    "user_phone": user_phone,
                    "query": state.get("query", ""),
                    "intent": state.get("intent"),
                    "provider": state.get("provider"),
                    "model": state.get("model"),
                    "response_length": len(response_text or ""),
                    "stream_error": stream_error or None,
                    "thinking_steps": state.get("thinking_steps", []),
                    "rag_evaluation": state.get("rag_evaluation", {}),
                }
            )
    except Exception:
        # Metrics persistence is best-effort and must not affect response streaming.
        return


async def stream_chat_events(request: Any, tools: AgentTooling) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Minimal Phase1 router executor.

    Backward compatibility design:
    - uses existing LLM stream/tooling via injected callbacks
    - yields the same event payload schema: {"text": "..."} or {"error": "..."}
    """
    session_id = getattr(request, "session_id", None)
    session_store = SessionStateService()
    context_manager = ContextManager()
    persisted_state = session_store.load_state(session_id) if session_id else {}
    persisted_history = persisted_state.get("conversation_messages", [])
    if not isinstance(persisted_history, list):
        persisted_history = []
    persisted_history = [str(m) for m in persisted_history if m]

    total_start = time.perf_counter()
    state: AgentState = {
        "query": getattr(request, "query", "") or "",
        "context": getattr(request, "context", {}) or {},
        "raw_content": getattr(request, "raw_content", "") or "",
        "provider": getattr(request, "provider", None),
        "model": getattr(request, "model", None),
        "session_id": session_id,
        "thinking_steps": [],
        "rag_evaluation": {},
    }

    intent_start = time.perf_counter()
    state["intent"] = classify_intent(state["query"])
    intent_step = _append_step(
        state,
        title="Understand user intent",
        content=f"Intent classified as '{state['intent']}'.",
        step_type="intent",
        start_at=intent_start,
    )
    yield {"type": "thinking_step", "step": intent_step}

    decompose_start = time.perf_counter()
    state["sub_queries"] = decompose_question(state["query"], state["intent"])
    decomposition_info = decomposition_metadata(state["query"], state.get("sub_queries", []))
    decompose_step = _append_step(
        state,
        title="Decompose question",
        content=(
            f"Prepared {decomposition_info['sub_query_count']} retrieval query unit(s) "
            f"for this request."
        ),
        step_type="decompose",
        start_at=decompose_start,
        metadata=decomposition_info,
    )
    yield {"type": "thinking_step", "step": decompose_step}

    state["trimmed_history"] = context_manager.trim_messages(persisted_history)

    if should_retrieve_context(state["intent"]):
        retrieval_start = time.perf_counter()
        retrieval_queries = state.get("sub_queries") or [state["query"]]
        retrieved_parts: List[str] = []
        all_retrieval_metrics: List[RetrievalMetric] = []
        results = await asyncio.gather(
            *(
                tools.build_context(sub_query, state["raw_content"], state["context"])
                for sub_query in retrieval_queries
            ),
            return_exceptions=True,
        )
        for idx, result in enumerate(results):
            if isinstance(result, Exception) or not result:
                continue
            context_str, metrics = result
            if not context_str:
                continue
            if len(retrieval_queries) > 1:
                retrieved_parts.append(f"[Sub-question {idx + 1}] {retrieval_queries[idx]}\n{context_str}")
            else:
                retrieved_parts.append(context_str)
            all_retrieval_metrics.extend(metrics)
        state["his_context"] = "\n\n".join(part for part in retrieved_parts if part.strip())
        source_counts: Dict[str, int] = {}
        for metric in all_retrieval_metrics:
            src = metric.get("source", "other")
            source_counts[src] = source_counts.get(src, 0) + 1
        state["rag_evaluation"] = {
            "retrieval_metrics": all_retrieval_metrics,
            "context_relevance": round(
                _avg([float(m.get("relevance_score", 0.0) or 0.0) for m in all_retrieval_metrics]),
                4,
            ),
            "retrieval_latency_ms": int((time.perf_counter() - retrieval_start) * 1000),
            "total_docs_retrieved": len(all_retrieval_metrics),
            "total_docs_used": 0,
        }
        retrieve_step = _append_step(
            state,
            title="Retrieve supporting context",
            content=(
                "Collected retrieval context across sources: "
                f"{', '.join(f'{k}={v}' for k, v in sorted(source_counts.items())) or 'none'}."
            ),
            step_type="retrieve",
            start_at=retrieval_start,
            metadata={"sources": source_counts},
        )
        yield {"type": "thinking_step", "step": retrieve_step}
        yield {"type": "rag_eval", "phase": "retrieval", "data": state["rag_evaluation"]}
    else:
        state["his_context"] = ""
        state["rag_evaluation"] = {
            "retrieval_metrics": [],
            "context_relevance": 0.0,
            "retrieval_latency_ms": 0,
            "total_docs_retrieved": 0,
            "total_docs_used": 0,
        }
        retrieve_step = _append_step(
            state,
            title="Skip retrieval",
            content="Simple intent detected, answer generated without external retrieval.",
            step_type="retrieve",
        )
        yield {"type": "thinking_step", "step": retrieve_step}

    if state.get("trimmed_history"):
        history_context = "\n".join(state["trimmed_history"])
        if state["his_context"]:
            state["his_context"] = (
                f"{state['his_context']}\n\nRecent conversation context:\n{history_context}"
            )
        else:
            state["his_context"] = f"Recent conversation context:\n{history_context}"

    state["his_context"] = _with_reasoning_scaffold(state.get("his_context", ""))
    synth_step = _append_step(
        state,
        title="Synthesize response",
        content="Generating response with structured reasoning scaffold and retrieved evidence.",
        step_type="synthesize",
    )
    yield {"type": "thinking_step", "step": synth_step}

    sync_chunk_queue: "queue.Queue[Any]" = queue.Queue()
    generation_start = time.perf_counter()

    def run_chat_stream() -> None:
        try:
            context_str = json.dumps(state["context"]) if state["context"] else "{}"
            raw_content_str = state["raw_content"] or ""
            for chunk in tools.chat_stream(
                state["query"],
                context_str,
                raw_content_str,
                state.get("his_context", ""),
                state.get("model"),
                state.get("provider"),
            ):
                if chunk:
                    sync_chunk_queue.put(chunk)
        except Exception as e:
            sync_chunk_queue.put(("error", str(e)))
        finally:
            sync_chunk_queue.put(None)

    asyncio.create_task(asyncio.to_thread(run_chat_stream))

    response_chunks: List[str] = []
    stream_error: str = ""
    while True:
        item = await asyncio.to_thread(sync_chunk_queue.get)
        if item is None:
            break
        if isinstance(item, tuple) and item[0] == "error":
            stream_error = item[1]
            yield {"error": item[1]}
            break
        response_chunks.append(item)
        yield {"text": item}

    if session_id:
        updated_history = list(persisted_history)
        if state.get("query"):
            updated_history.append(f"User: {state['query']}")
        if response_chunks:
            updated_history.append(f"Assistant: {''.join(response_chunks).strip()}")
        elif stream_error:
            updated_history.append(f"AssistantError: {stream_error}")

        session_store.save_state(
            session_id,
            {
                "intent": state.get("intent"),
                "sub_queries": state.get("sub_queries", []),
                "his_context": state.get("his_context", ""),
                "conversation_messages": context_manager.trim_messages(updated_history),
            },
        )

    answer_text = "".join(response_chunks).strip()

    # Evaluate: use RAGAS (async) when enabled, otherwise keyword overlap (sync)
    from config.settings import RAGAS_ENABLED
    if RAGAS_ENABLED:
        rag_eval = await _finalize_rag_eval_async(state, answer_text)
    else:
        rag_eval = _finalize_rag_eval(state, answer_text)

    rag_eval["generation_latency_ms"] = int((time.perf_counter() - generation_start) * 1000)
    rag_eval["total_latency_ms"] = int((time.perf_counter() - total_start) * 1000)
    eval_step = _append_step(
        state,
        title="Evaluate response quality",
        content=(
            f"[{rag_eval.get('eval_method', 'keyword_overlap')}] "
            f"faithfulness={rag_eval.get('answer_faithfulness', 0):.2f}, "
            f"coverage={rag_eval.get('answer_coverage', 0):.2f}, "
            f"quality={rag_eval.get('quality_score', 0):.2f}"
        ),
        step_type="evaluate",
        metadata={
            "docs_retrieved": rag_eval.get("total_docs_retrieved", 0),
            "docs_used": rag_eval.get("total_docs_used", 0),
            "eval_method": rag_eval.get("eval_method", "keyword_overlap"),
        },
    )
    yield {"type": "thinking_step", "step": eval_step}
    yield {"type": "rag_eval", "phase": "answer", "data": rag_eval}
    _check_quality_alert(state, rag_eval)
    _persist_quality_metrics(state, answer_text, stream_error)
