"""Task context — correlation IDs and LLM state."""

from typing import Optional
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class TaskContext:
    """Context for a single task execution."""

    task_id: str
    task_context_id: str  # For OpenTelemetry correlation
    phase: str
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    llm_state: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)

    def update_phase(self, new_phase: str):
        """Update phase and timestamp."""
        self.phase = new_phase
        self.updated_at = datetime.now().isoformat()

    def to_trace_attributes(self) -> dict:
        """Convert to OpenTelemetry span attributes."""
        return {
            "task_id": self.task_id,
            "task_context_id": self.task_context_id,
            "phase": self.phase,
            "created_at": self.created_at,
        }


class TaskContextManager:
    """Manages task contexts in memory."""

    def __init__(self):
        self._contexts: dict[str, TaskContext] = {}

    def create_context(self, task_id: str, phase: str) -> TaskContext:
        """Create task context with correlation ID."""
        context_id = f"task_{task_id}"
        context = TaskContext(
            task_id=task_id,
            task_context_id=context_id,
            phase=phase,
        )
        self._contexts[task_id] = context
        return context

    def get_context(self, task_id: str) -> Optional[TaskContext]:
        """Get task context by ID."""
        return self._contexts.get(task_id)

    def remove_context(self, task_id: str) -> Optional[TaskContext]:
        """Remove and return task context."""
        return self._contexts.pop(task_id, None)
