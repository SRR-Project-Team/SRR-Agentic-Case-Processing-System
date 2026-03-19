from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional
from uuid import uuid4


SourceType = Literal["ICC", "TMO", "RCC", "UNKNOWN"]


@dataclass
class TaskState:
    """Unified task state for ability-based case processing."""

    task_id: str = field(default_factory=lambda: uuid4().hex)
    task_type: str = "create_case"
    source_type: SourceType = "UNKNOWN"
    fields: Dict[str, Any] = field(default_factory=dict)
    missing_fields: List[str] = field(default_factory=list)
    steps_done: List[str] = field(default_factory=list)
    steps_todo: List[str] = field(default_factory=list)
    quality_score: float = 0.0
    validation_errors: List[str] = field(default_factory=list)
    error_log: List[str] = field(default_factory=list)
    retry_record: Dict[str, int] = field(default_factory=dict)
    external_data: Dict[str, Any] = field(default_factory=dict)
    similar_cases: List[Dict[str, Any]] = field(default_factory=list)
    has_referral_history: bool = False
    referral_annotations: List[Dict[str, Any]] = field(default_factory=list)
    department_routing: Dict[str, Any] = field(default_factory=dict)
    summary: str = ""
    raw_content: str = ""
    file_path: str = ""
    file_name: str = ""
    case_id: Optional[int] = None

    def mark_step_done(self, step_name: str) -> None:
        if step_name and step_name not in self.steps_done:
            self.steps_done.append(step_name)
        if step_name and step_name in self.steps_todo:
            self.steps_todo.remove(step_name)

    def add_error(self, error_msg: str) -> None:
        if error_msg:
            self.error_log.append(error_msg)

    def increase_retry(self, step_name: str) -> None:
        if not step_name:
            return
        self.retry_record[step_name] = self.retry_record.get(step_name, 0) + 1
