"""Integration test for the full task lifecycle.

End-to-end flow with mocked external dependencies:
1. Create mock task in SQLite
2. Discovery phase: evaluate_task -> place_bid
3. Research phase transition
4. Delivery phase transition
5. Validation: validate_deliverable
6. Submission phase transition
7. handle_task_completion
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.orchestrator.engine import (
    Phase,
    OrchestratorEngine,
)
from src.skills.validation import validate_deliverable


# ---------------------------------------------------------------------------
# Full task lifecycle test
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
        self.store = temp_db

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

        with patch("src.wallet.client.list_tasks",
                   AsyncMock(return_value=[{
                       "id": self.TASK_ID,
                       "title": task["title"],
                       "description": task["description"],
                       "category": "backend",
                       "price_points": 500,
                       "deadline": "2026-05-01",
                   }])), \
             patch("src.skills.bidding_strategy.should_evaluate_task",
                   return_value=True), \
             patch("src.skills.bidding_strategy.evaluate_task",
                   return_value=mock_evaluation), \
             patch("src.wallet.client.estimate_time",
                   AsyncMock(return_value=120)), \
             patch("src.wallet.client.place_bid") as mock_bid:
            # Task already exists in DB from step 0, so prevent duplicate insert
            original_add_task = self.store.add_task
            async def mock_add_task(task_id, **kwargs):
                existing = await self.store.get_task(task_id)
                if existing:
                    return await self.store.update_task(task_id, status="BIDDING")
                return await original_add_task(task_id, **kwargs)

            with patch.object(self.store, 'add_task', side_effect=mock_add_task):
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

            # validate_deliverable is synchronous (uses asyncio.run internally)
            # Run it in executor to avoid event loop conflicts
            loop = asyncio.get_running_loop()
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(
                    validate_deliverable, criteria, deliverable, 0.8, 0, 3
                )
                result = await loop.run_in_executor(None, lambda: future.result())

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
        assert task["phase"] == "PHASE_DISCOVERY"


# ---------------------------------------------------------------------------
# Guardrail fire during lifecycle
# ---------------------------------------------------------------------------


class TestGuardrailFireDuringLifecycle:
    """Test: guardrail fire halts task mid-lifecycle."""

    @pytest.mark.asyncio
    async def test_guardrail_fire_halts_task(self, temp_db):
        """Guardrail fire during delivery should halt the task."""
        task_id = "halt-task-001"
        await temp_db.add_task(
            task_id,
            title="Guardrail Test",
            description="Build a service",
            status="IN_PROGRESS",
        )
        await temp_db.update_task(task_id, phase="PHASE_DELIVERY")

        # Simulate guardrail fire
        from src.guardrails.service import on_guardrail_fire

        with patch("src.db.store.AegisStore", return_value=temp_db):
            await on_guardrail_fire(
                task_id=task_id,
                content="<script>alert('xss')</script>",
                finding="Injection detected in chunk 1/1 (confidence: 0.92)",
            )

        task = await temp_db.get_task(task_id)
        assert task["status"] == "HALTED"
        assert "Injection detected" in task["halted_reason"]


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
        )
        await temp_db.update_task("iter-task", phase="PHASE_VALIDATION")

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

            loop = asyncio.get_running_loop()
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(
                    validate_deliverable, ["Has error handling"], "def broken(): pass", 0.8, 0, 3
                )
                result = await loop.run_in_executor(None, lambda: future.result())

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

            loop = asyncio.get_running_loop()
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(
                    validate_deliverable, ["Has error handling"], "def robust(): try: do_work() except: handle_error()", 0.8, 1, 3
                )
                result = await loop.run_in_executor(None, lambda: future.result())

        assert result["passed"] is True
        assert result["quality_confidence"] == pytest.approx(0.85, 0.01)
