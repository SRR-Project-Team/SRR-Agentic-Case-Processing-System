#!/usr/bin/env python3
"""Persist lightweight agent session state in chat_sessions table.

Part of the three-layer memory strategy (see docs/MEMORY_STRATEGY.md):
- Task memory: TaskState (ephemeral, per process_case)
- Case memory: SessionStateService (this module) — cross-session case context
- Domain memory: UserFeedbackService — correction rules in knowledge_docs
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from database import get_db_manager
from database.models import ChatSession


class SessionStateService:
    """Load/save session state for long-running agent interactions.

    Implements case memory: persists case draft, sub-tasks, and progress
    across sessions. See docs/MEMORY_STRATEGY.md.
    """

    def __init__(self) -> None:
        self.db = get_db_manager()

    def load_state(self, session_id: str) -> Dict[str, Any]:
        if not session_id:
            return {}
        session = self.db.get_session()
        try:
            chat = session.query(ChatSession).filter(ChatSession.session_id == session_id).first()
            if not chat or not getattr(chat, "session_state", None):
                return {}
            raw = chat.session_state
            if isinstance(raw, dict):
                return raw
            return json.loads(raw)
        except Exception:
            return {}
        finally:
            session.close()

    def save_state(self, session_id: str, state: Dict[str, Any]) -> bool:
        if not session_id:
            return False
        session = self.db.get_session()
        try:
            chat = session.query(ChatSession).filter(ChatSession.session_id == session_id).first()
            if not chat:
                return False
            chat.session_state = json.dumps(state or {}, ensure_ascii=False)
            session.commit()
            return True
        except Exception:
            session.rollback()
            return False
        finally:
            session.close()
