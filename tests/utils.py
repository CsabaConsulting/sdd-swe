"""Test utility helpers for Aegis test suite."""

from typing import Optional
import json


# ---------------------------------------------------------------------------
# Mock task factory
# ---------------------------------------------------------------------------


def create_mock_task(
    task_id: str = "test-task-001",
    title: str = "Test Task",
    description: str = "A test task for unit testing",
    acceptance_criteria: Optional[list] = None,
    category: str = "testing",
    points: int = 100,
    deadline: Optional[str] = None,
    status: str = "DISCOVERED",
    phase: Optional[str] = None,
    price_points_bid: Optional[int] = None,
    estimated_minutes: Optional[int] = None,
    metadata: Optional[dict] = None,
) -> dict:
    """Build a realistic task dict suitable for DB insertion or API mocks.

    Args:
        task_id: Unique task identifier.
        title: Task title.
        description: Task description.
        acceptance_criteria: List of criteria strings.
        category: Task category (e.g., "backend", "testing").
        points: Points reward.
        deadline: ISO-8601 deadline string.
        status: Initial task status (e.g., "DISCOVERED", "BIDDING").
        phase: Current phase (e.g., "PHASE_DISCOVERY").
        price_points_bid: Points bid for this task.
        estimated_minutes: Estimated duration in minutes.
        metadata: Arbitrary metadata dict.

    Returns:
        Dict matching the schema expected by AegisStore / mock client.
    """
    if acceptance_criteria is None:
        acceptance_criteria = ["Test criterion 1", "Test criterion 2"]

    return {
        "id": task_id,
        "title": title,
        "description": description,
        "acceptance_criteria": acceptance_criteria,
        "category": category,
        "points": points,
        "deadline": deadline,
        "status": status,
        "phase": phase,
        "price_points_bid": price_points_bid,
        "estimated_minutes": estimated_minutes,
        "metadata": metadata or {},
    }


# ---------------------------------------------------------------------------
# Status assertions
# ---------------------------------------------------------------------------


def assert_task_status(task: dict, expected_status: str) -> None:
    """Assert that a task dict has the expected status.

    Args:
        task: Task dict from AegisStore.get_task() or mock client.
        expected_status: Expected status string (e.g., "BIDDING").

    Raises:
        AssertionError: If status does not match.
    """
    actual = task.get("status")
    assert actual == expected_status, (
        f"Expected task status {expected_status!r}, got {actual!r}"
    )


def assert_task_phase(task: dict, expected_phase: str) -> None:
    """Assert that a task dict is in the expected phase."""
    actual = task.get("phase")
    assert actual == expected_phase, (
        f"Expected task phase {expected_phase!r}, got {actual!r}"
    )


def assert_points_in_range(task: dict, min_points: int, max_points: int) -> None:
    """Assert task points are within the expected range."""
    pts = task.get("points", 0)
    assert min_points <= pts <= max_points, (
        f"Task points {pts} outside expected range [{min_points}, {max_points}]"
    )


# ---------------------------------------------------------------------------
# JSON / serialisation helpers
# ---------------------------------------------------------------------------


def json_serialize(obj) -> str:
    """Deterministic JSON serialisation for comparison in tests."""
    return json.dumps(obj, sort_keys=True, default=str)


def json_contains(actual: dict | str, expected: dict) -> bool:
    """Check that *expected* key-value pairs are present in *actual*.

    Works with both dicts and JSON strings.
    """
    if isinstance(actual, str):
        actual = json.loads(actual)
    for key, value in expected.items():
        assert key in actual, f"Missing key {key!r} in {actual}"
        assert actual[key] == value, (
            f"Key {key!r}: expected {value!r}, got {actual[key]!r}"
        )
    return True


# ---------------------------------------------------------------------------
# LLM response helpers
# ---------------------------------------------------------------------------


def parse_llm_eval_response(text: str) -> dict:
    """Parse a structured LLM evaluation response.

    Expects text like::

        PASS
        Score: 0.92
        Some explanatory text.

    Returns:
        Dict with keys ``verdict`` ("PASS" or "FAIL") and ``score`` (float).
    """
    lines = text.strip().splitlines()
    verdict = lines[0].strip().upper() if lines else "UNKNOWN"
    score = 0.0
    for line in lines[1:]:
        if line.lower().startswith("score:"):
            try:
                score = float(line.split(":", 1)[1].strip())
            except (ValueError, IndexError):
                pass
            break
    return {"verdict": verdict, "score": score}
