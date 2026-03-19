"""
Agent package (Phase1 scaffold).

This package provides a minimal, backward-compatible orchestration layer
for chat routing. It is guarded by feature flags and can be safely disabled.
"""

from .graph import process_case, stream_chat_events
from .task_state import TaskState
from .tools import AgentTooling

__all__ = ["stream_chat_events", "process_case", "TaskState", "AgentTooling"]
