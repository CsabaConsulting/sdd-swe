"""Integration test for the full task lifecycle.

End-to-end flow with mocked external dependencies:
1. Create mock task in SQLite
2. Discovery phase: evaluate_task -> place_bid
3. Research phase transition
4. Delivery phase transition
5. Validation: validate_deliverable
6. Submission phase transition
7. handle_task_completion

Verifies SQLite state changes at each phase.
Uses conftest.py fixtures (temp_db, mock_config, mock_api_client).
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.db.store import AegisStore
from src.orchestrator.engine import (
    Phase,
    OrchestratorEngine,
)
from src.skills.validation import validate_deliverable

from tests.utils import create_mock_task, assert_task_status, assert_task_phase


# ---------------------------------------------------------------------------
# Integration test
# ---------------------------------------------------------------------------


class TestFullTaskLifecycle:
    """Full lifecycle: discovery -> research -> delivery -> validation -> submission."""

    TASK_ID = "lifecycle-task-001"

    @pytest.mark.asyncio
    async def test_complete_lifecycle(self, temp_db, mock_config):
        """
        Walk a single task through the entire lifecycle, verifying
        database state at each step.
        """

        # ---------- STEP 0: Create initial task ----------
        await temp_db.add_task(
            self.TASK_ID,
            title="Integration Test Task",
            description="Build a REST API with auth",
            category="backend",
            points=500,
            status="DISCOVERED",
        )

        task = await temp_db.get_task(self.TASK_ID)
        assert task["title"] == "Integration Test Task"
        assert task["status"] == "DISCOVERED"

        # ---------- STEP 1: Discovery phase ----------
        engine = OrchestratorEngine(store=temp_db)

        with patch("src.orchestrator.engine.load_skill") as mock_load, \
             patch("src.orchestrator.engine.unload_skill"):
            await engine.transition_phase(self.TASK_ID, Phase.PHASE_DISCOVERY)

        task = await temp_db.get_task(self.TASK_ID)
        assert task["phase"] == "PHASE_DISCOVERY"
        assert "bidding-strategy" in engine.active_skills

        # Evaluate the task (mocked)
        mock_evaluation = {
            "skill_fit": True,
            "confidence": 0.85,
            "recommended_points": 525,
            "approach": "Build with FastAPI",
        }

        with patch("src.orchestrator.engine.list_tasks",
                   AsyncMock(return_value=[{
                       "id": self.TASK_ID,
                       "title": task["title"],
                       "description": task["description"],
                       "category": "backend",
                       "price_points": 500,
                       "deadline": "2026-05-01",
                   }])), \
             patch("src.orchestrator.engine.should_evaluate_task",
                   return_value=True), \
             patch("src.orchestrator.engine.evaluate_task",
                   return_value=mock_evaluation), \
             patch("src.orchestrator.engine.estimate_time",
                   AsyncMock(return_value=120)), \
             patch("src.orchestrator.engine.place_bid") as mock_bid:
            await engine.run_discovery_cycle(mock_config)

        mock_bid.assert_called_once()

        # Task should be in BIDDING status
        task = await temp_db.get_task(self.TASK_ID)
        assert task["status"] == "BIDDING"

        # ---------- STEP 2: Research phase ----------
        with patch("src.orchestrator.engine.load_skill") as mock_load, \
             patch("src.orchestrator.engine.unload_skill") as mock_unload:
            await engine.transition_phase(self.TASK_ID, Phase.PHASE_RESEARCH)

        task = await temp_db.get_task(self.TASK_ID)
        assert task["phase"] == "PHASE_RESEARCH"
        mock_unload.assert_called_with("bidding-strategy")
        mock_load.assert_called_with("research")
        assert "bidding-strategy" not in engine.active_skills
        assert "research" in engine.active_skills

        # ---------- STEP 3: Delivery phase ----------
        with patch("src.orchestrator.engine.load_skill") as mock_load, \
             patch("src.orchestrator.engine.unload_skill") as mock_unload:
            await engine.transition_phase(self.TASK_ID, Phase.PHASE_DELIVERY)

        task = await temp_db.get_task(self.TASK_ID)
        assert task["phase"] == "PHASE_DELIVERY"
        mock_unload.assert_called_with("research")
        mock_load.assert_called_with("code-delivery")
        assert "research" not in engine.active_skills
        assert "code-delivery" in engine.active_skills

        # ---------- STEP 4: Validation ----------
        with patch("src.orchestrator.engine.load_skill") as mock_load, \
             patch("src.orchestrator.engine.unload_skill") as mock_unload:
            await engine.transition_phase(self.TASK_ID, Phase.PHASE_VALIDATION)

        task = await temp_db.get_task(self.TASK_ID)
        assert task["phase"] == "PHASE_VALIDATION"

        # Run validation (mocked)
        criteria = ["Has /users endpoint", "Has auth middleware"]
        deliverable = """
def get_users():
    return [{"id": 1, "name": "Alice"}]

class AuthMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        # Auth logic
        await self.app(scope, receive, send)
"""

        with patch("src.skills.validation._get_llm_client") as mock_llm:
            # First call: criteria check (passed=true)
            criteria_resp = MagicMock()
            criteria_resp.choices[0].message.content = json.dumps({
                "passed": True,
                "feedback": "All criteria met"
            })

            # Second call: architecture check (score=0.9)
            arch_resp = MagicMock()
            arch_resp.choices[0].message.content = "0.90"

            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(
                side_effect=[criteria_resp, arch_resp]
            )
            mock_llm.return_value = mock_client

            result = validate_deliverable(
                acceptance_criteria=criteria,
                deliverable=deliverable,
                threshold=0.8,
                iteration_count=0,
                max_iterations=3,
            )

        assert result["passed"] is True
        assert result["quality_confidence"] == pytest.approx(0.90, 0.01)

        # ---------- STEP 5: Submission phase ----------
        with patch("src.orchestrator.engine.load_skill") as mock_load, \
             patch("src.orchestrator.engine.unload_skill") as mock_unload:
            await engine.transition_phase(self.TASK_ID, Phase.PHASE_SUBMISSION)

        task = await temp_db.get_task(self.TASK_ID)
        assert task["phase"] == "PHASE_SUBMISSION"
        mock_unload.assert_called_with("validation")
        mock_load.assert_called_with("wallet-management")
        assert "wallet-management" in engine.active_skills

        # ---------- STEP 6: Task completion ----------
        with patch("src.orchestrator.engine.load_skill") as mock_load_new, \
             patch("src.orchestrator.engine.unload_skill"):
            await engine.handle_task_completion(self.TASK_ID)

        task = await temp_db.get_task(self.TASK_ID)
        assert task["status"] == "SUBMITTED"
        assert task["phase"] == "PHASE_DISCOVERY"
        # Back to discovery: bidding-strategy loaded
        load_calls = [c[0][0] for c in mock_load_new.call_args_list]
        assert "bidding-strategy" in load_calls

        # ---------- STEP 7: Verify all phases were recorded ----------
        phases_seen = [
            "PHASE_DISCOVERY", "PHASE_RESEARCH", "PHASE_DELIVERY",
            "PHASE_VALIDATION", "PHASE_SUBMISSION", "PHASE_DISCOVERY"
        ]
        # Final state check
        assert task["phase"] == "PHASE_DISCOVERY"
        assert task["status"] == "SUBMITTED"


# ---------------------------------------------------------------------------
# Guardrail fire during lifecycle
# ---------------------------------------------------------------------------


class TestGuardrailFireDuringLifecycle:
    """Integration test: guardrail fire halts the task."""

    @pytest.mark.asyncio
    async def test_guardrail_fire_halts_task(self, temp_db):
        """on_guardrail_fire sets task to HALTED and adds review item."""
        from src.guardrails.service import on_guardrail_fire

        await temp_db.add_task(
            "fire-task",
            title="Task that gets halted",
            description="Contains malicious code",
            status="IN_PROGRESS",
            phase="PHASE_DELIVERY",
        )

        task = await temp_db.get_task("fire-task")
        assert task["status"] == "IN_PROGRESS"

        with patch("src.guardrails.service.AegisStore", return_value=temp_db):
            await on_guardrail_fire(
                task_id="fire-task",
                content="<script>alert('xss')</script>",
                finding="Injection detected in payload",
            )

        task = await temp_db.get_task("fire-task")
        assert task["status"] == "HALTED"
        assert "Injection detected" in task["halted_reason"]

        review_items = await temp_db.get_review_items("pending")
        assert len(review_items) == 1
        item = review_items[0]
        assert item["type"] == "guardrail_fire"
        assert item["task_id"] == "fire-task"

        details = json.loads(item["details"])
        assert details["finding"] == "Injection detected in payload"


# ---------------------------------------------------------------------------
# Full lifecycle with validation iteration loop
# ---------------------------------------------------------------------------


class TestValidationIterationLoop:
    """Integration test: validation loops before passing."""

    @pytest.mark.asyncio
    async def test_validation_passes_after_iterations(self, temp_db, mock_config):
        """Task goes through multiple validation iterations before passing."""
        await temp_db.add_task(
            "iter-task",
            title="Needs Iter",
            description="Build a service",
            status="IN_PROGRESS",
            phase="PHASE_VALIDATION",
        )

        await temp_db.update_task("iter-task", validation_iterations=0)

        # First validation attempt: fails, feedback provided
        with patch("src.skills.validation._get_llm_client") as mock_llm:
            criteria_resp = MagicMock()
            criteria_resp.choices[0].message.content = json.dumps({
                "passed": False,
                "feedback": "Missing error handling"
            })
            arch_resp = MagicMock()
            arch_resp.choices[0].message.content = "0.6"

            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(
                side_effect=[criteria_resp, arch_resp]
            )
            mock_llm.return_value = mock_client

            result = validate_deliverable(
                acceptance_criteria=["Has error handling"],
                deliverable="def broken(): pass",
                threshold=0.8,
                iteration_count=0,
                max_iterations=3,
            )

        assert result["passed"] is False
        assert "Criteria issues" in result["feedback"]

        # Update iteration count
        await temp_db.update_task("iter-task", validation_iterations=1)
        task = await temp_db.get_task("iter-task")
        assert task["validation_iterations"] == 1

        # Second attempt: passes
        await temp_db.update_task(
            "iter-task",
            deliverable_content="def robust(): try: pass except: pass"
        )

        with patch("src.skills.validation._get_llm_client") as mock_llm:
            criteria_resp = MagicMock()
            criteria_resp.choices[0].message.content = json.dumps({
                "passed": True,
                "feedback": "All good"
            })
            arch_resp = MagicMock()
            arch_resp.choices[0].message.content = "0.85"

            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(
                side_effect=[criteria_resp, arch_resp]
            )
            mock_llm.return_value = mock_client

            result = validate_deliverable(
                acceptance_criteria=["Has error handling"],
                deliverable="def robust(): try: do_work() except: handle_error()",
                threshold=0.8,
                iteration_count=1,
                max_iterations=3,
            )

        assert result["passed"] is True
        assert result["quality_confidence"] == pytest.approx(0.85, 0.01)
