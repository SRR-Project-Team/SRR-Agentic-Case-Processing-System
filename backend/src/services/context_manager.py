#!/usr/bin/env python3
"""Simple token-aware chat context trimming."""

from __future__ import annotations

from typing import List


class ContextManager:
    """Keep recent context under a target token budget."""

    def __init__(self, max_tokens: int = 6000) -> None:
        self.max_tokens = max_tokens

    def _estimate_tokens(self, text: str) -> int:
        # Lightweight approximation: 1 token ~= 4 chars for mixed EN/ZH content.
        return max(1, len(text or "") // 4)

    def trim_messages(self, messages: List[str]) -> List[str]:
        if not messages:
            return []
        total = 0
        kept: List[str] = []
        for message in reversed(messages):
            cost = self._estimate_tokens(message)
            if total + cost > self.max_tokens:
                break
            kept.append(message)
            total += cost
        kept.reverse()
        return kept
