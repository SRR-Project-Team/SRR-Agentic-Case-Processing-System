from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Generator, List, Optional, Tuple


# Return type for build_context: (context_text, retrieval_metrics)
ContextResult = Tuple[str, List[Dict[str, Any]]]


@dataclass(frozen=True)
class AgentTooling:
    """
    Tool adapter contract for agent router.

    `build_context` returns (context_string, retrieval_metrics) where metrics
    carry the original pgvector similarity scores from retrieval.
    `chat_stream` should proxy to existing LLM streaming API.
    """

    build_context: Callable[[str, str, Dict[str, Any]], Awaitable[ContextResult]]
    chat_stream: Callable[
        [str, str, str, str, Optional[str], Optional[str]],
        Generator[str, None, None],
    ]
