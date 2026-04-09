"""Bidding strategy — task evaluation (stub implementation)."""

from typing import TypedDict
from src.config.loader import AegisConfig


class TaskEvaluation(TypedDict):
    """Result from task evaluation."""
    skill_fit: bool
    points_to_effort: float
    confidence: float
    recommended_points: int
    approach: str


def should_evaluate_task(task: dict, specializations: list[str] = None) -> bool:
    """Determine if agent should bid on task.

    Args:
        task: Task dict from /tasks endpoint
        specializations: Optional list of specialization categories

    Returns:
        True if task should be evaluated
    """
    # Filter 1: Only open tasks
    if task.get("status") != "open":
        return False

    # Filter 2: Specialization match (if configured)
    if specializations and task.get("category") not in specializations:
        return False

    return True


async def evaluate_task(task: dict, config: AegisConfig) -> TaskEvaluation:
    """Evaluate task for bidding (stub).

    In production: LLM analyzes complexity, checks specialization, calculates ratio.
    For hackathon: returns passing stub with high confidence.

    Args:
        task: Task dict from /tasks
        config: Application config

    Returns:
        TaskEvaluation with bid recommendation
    """
    return TaskEvaluation(
        skill_fit=True,
        points_to_effort=task.get("price_points", 100) / 60.0,
        confidence=0.85,
        recommended_points=task.get("price_points", 100),
        approach="Implement solution following best practices with tests and documentation.",
    )


# Add missing import to wallet client for list_tasks
async def _add_list_tasks_stub():
    """Add list_tasks function to wallet client."""
    pass
