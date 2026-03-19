import re
from typing import Dict, List

from .state import IntentType


_GREETING_KEYWORDS = (
    "hi",
    "hello",
    "hey",
    "你好",
    "您好",
    "早晨",
    "早上好",
    "thanks",
    "thank you",
)

_COMPLEX_HINTS = (
    "compare",
    "analysis",
    "analyze",
    "总结",
    "分析",
    "比较",
    "相似",
    "historical",
    "history",
    "why",
    "how",
)

_REPLY_KEYWORDS = (
    "reply",
    "draft",
    "回复",
    "草稿",
    "回覆",
)

_STATUS_KEYWORDS = (
    "status",
    "progress",
    "进度",
    "狀態",
    "状态",
)

_HISTORY_KEYWORDS = (
    "history",
    "historical",
    "past case",
    "歷史",
    "历史",
    "相似案件",
)

_RETRIEVAL_KEYWORDS = (
    "tree", "inventory", "slope", "case", "report", "detail",
    "inspection", "record", "document", "file", "data", "info",
    "give", "show", "find", "list", "get", "tell", "what", "which",
    "樹", "樹木", "斜坡", "個案", "清單", "報告", "記錄",
    "查", "找", "給", "顯示", "檢查", "資料", "詳情",
    "树", "树木", "个案", "清单", "报告", "记录", "详情",
)

_DOMAIN_ID_PATTERN = re.compile(
    r"(?:"
    r"[A-Za-z]{1,3}\d{4,}"      # slope IDs: SA0008, 11NE-D/C123
    r"|TS\d+"                    # tree numbers: TS006
    r"|\d{1,2}-\d{8,}"          # case numbers: 3-9057690272
    r")",
    re.IGNORECASE,
)


def classify_intent(query: str) -> IntentType:
    """
    Intent routing for RAG system — defaults to retrieval (complex).

    Only short, purely conversational queries without domain entities
    are classified as simple/greeting to skip retrieval.
    """
    q = (query or "").strip().lower()
    if not q:
        return "chat_query"

    # Greeting only when the entire message is a short social phrase
    if any(token in q for token in _GREETING_KEYWORDS) and len(q) <= 20:
        return "greeting"

    if any(token in q for token in _REPLY_KEYWORDS):
        return "generate_reply"

    if any(token in q for token in _STATUS_KEYWORDS):
        return "check_status"

    if any(token in q for token in _HISTORY_KEYWORDS):
        return "search_history"

    # Domain entity IDs (slope/tree/case numbers) always need retrieval
    if _DOMAIN_ID_PATTERN.search(q):
        return "chat_query"

    # Domain vocabulary that implies data lookup
    if any(kw in q for kw in _RETRIEVAL_KEYWORDS):
        return "chat_query"

    if any(token in q for token in _COMPLEX_HINTS):
        return "chat_query"

    # Only very short queries with no digits qualify as simple
    if len(q) <= 30 and not any(c.isdigit() for c in q):
        return "chat_query"

    return "chat_query"


def should_retrieve_context(intent: IntentType) -> bool:
    """Greeting is the only intent that skips retrieval."""
    return intent != "greeting"


def _dedupe_keep_order(items: List[str]) -> List[str]:
    seen = set()
    ordered: List[str] = []
    for item in items:
        key = item.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        ordered.append(item.strip())
    return ordered


def decompose_question(query: str, intent: IntentType, max_parts: int = 3) -> List[str]:
    """
    Split complex multi-part questions into smaller retrieval units.

    The split is intentionally conservative to avoid damaging semantic queries.
    """
    text = " ".join((query or "").strip().split())
    if not text:
        return []
    if intent not in ("chat_query", "search_history", "check_status"):
        return [text]

    # Prefer punctuation and explicit "also/另外/同时" style connectors.
    parts = re.split(
        r"(?:[?？;；]|(?:\balso\b)|(?:\bthen\b)|另外|還有|还有|同時|同时|其次)",
        text,
        flags=re.IGNORECASE,
    )
    cleaned = [p.strip(" ,，。:：") for p in parts if p and p.strip(" ,，。:：")]
    unique_parts = _dedupe_keep_order(cleaned)

    if len(unique_parts) <= 1:
        return [text]
    return unique_parts[:max_parts]


def decomposition_metadata(query: str, sub_queries: List[str]) -> Dict[str, int]:
    """Provide lightweight decomposition metadata for observability."""
    normalized_query = " ".join((query or "").split())
    normalized_parts = [p for p in sub_queries if p]
    return {
        "query_length": len(normalized_query),
        "sub_query_count": len(normalized_parts),
    }


def keyword_overlap_score(reference: str, text: str) -> float:
    """Cheap relevance proxy used for retrieval/answer quality scoring."""
    ref_terms = set(re.findall(r"[\w\u4e00-\u9fff]{2,}", (reference or "").lower()))
    txt_terms = set(re.findall(r"[\w\u4e00-\u9fff]{2,}", (text or "").lower()))
    if not ref_terms:
        return 0.0
    return len(ref_terms & txt_terms) / max(len(ref_terms), 1)
