from typing import Any, Dict, List, Literal, Optional, TypedDict


IntentType = Literal[
    "create_case",
    "search_history",
    "generate_reply",
    "chat_query",
    "check_status",
    "greeting",
]


class ThinkingStep(TypedDict, total=False):
    step_id: int
    title: str
    content: str
    step_type: Literal["intent", "decompose", "retrieve", "synthesize", "evaluate"]
    duration_ms: int
    metadata: Dict[str, Any]


class RetrievalMetric(TypedDict, total=False):
    source: str
    doc_id: str
    doc_title: str
    similarity_score: float
    relevance_score: float
    used_in_answer: bool
    snippet: str


class RAGEvaluation(TypedDict, total=False):
    retrieval_metrics: List[RetrievalMetric]
    context_relevance: float
    answer_faithfulness: float
    answer_coverage: float
    faithfulness_matched: List[str]
    faithfulness_total: int
    coverage_matched: List[str]
    coverage_missed: List[str]
    retrieval_latency_ms: int
    generation_latency_ms: int
    total_latency_ms: int
    total_docs_retrieved: int
    total_docs_used: int
    quality_score: float


class AgentState(TypedDict, total=False):
    """State payload for router flow with CoT and RAG quality telemetry."""

    query: str
    context: Dict[str, Any]
    raw_content: str
    provider: Optional[str]
    model: Optional[str]
    session_id: Optional[str]
    intent: IntentType
    sub_queries: List[str]
    his_context: str
    trimmed_history: List[str]
    thinking_steps: List[ThinkingStep]
    rag_evaluation: RAGEvaluation
