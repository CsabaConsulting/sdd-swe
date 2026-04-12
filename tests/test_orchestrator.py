"""Unit tests for the orchestrator engine (finite state machine).

Covers:
- Phase transitions (DISCOVERY -> RESEARCH -> DELIVERY -> VALIDATION -> SUBMISSION)
- Skill loading/unloading during transitions
- Task status updates in SQLite
- Invalid phase raises ValueError
- handle_task_completion resets to DISCOVERY
- run_discovery_cycle integration (mocked)
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.orchestrator.engine import (
    Phase,
    PHASE_TRANSITIONS,
    OrchestratorEngine,
)


# ---------------------------------------------------------------------------
# Phase transition fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_store(temp_db):
    """Return the temp_db fixture for orchestrator tests."""
    return temp_db


@pytest.fixture
def engine(mock_store):
    """Create an OrchestratorEngine with an empty skill set."""
    return OrchestratorEngine(store=mock_store)


# ---------------------------------------------------------------------------
# Phase transitions
# ---------------------------------------------------------------------------


class TestPhaseTransitions:
    """Orchestrator transitions between phases with correct skill ops."""

    @pytest.mark.asyncio
    async def test_initial_transition_to_discovery(self, engine):
        """init() transitions to PHASE_DISCOVERY and loads bidding-strategy skill."""
        with patch("src.orchestrator.engine.load_skill") as mock_load, \
             patch("src.orchestrator.engine.unload_skill") as mock_unload:
            await engine.init()

        mock_load.assert_called_once_with("bidding-strategy")
        assert "bidding-strategy" in engine.active_skills

    @pytest.mark.asyncio
    async def test_transition_discovers_task_phase_update(self, engine, mock_store):
        """Transition to RESEARCH updates the task phase in SQLite."""
        await mock_store.add_task(
            "task-1", title="Test", status="BIDDING"
        )
        await mock_store.update_task("task-1", phase="PHASE_DISCOVERY")

        with patch("src.orchestrator.engine.load_skill"), \
             patch("src.orchestrator.engine.unload_skill"):
            await engine.transition_phase("task-1", Phase.PHASE_RESEARCH)

        task = await mock_store.get_task("task-1")
        assert task["phase"] == "PHASE_RESEARCH"

    @pytest.mark.asyncio
    async def test_full_transition_sequence(self, engine, mock_store):
        """Walk through all 5 phases and verify skill tracking."""
        await mock_store.add_task("task-1", title="Full Lifecycle", status="BIDDING")

        transitions = [
            Phase.PHASE_DISCOVERY,
            Phase.PHASE_RESEARCH,
            Phase.PHASE_DELIVERY,
            Phase.PHASE_VALIDATION,
            Phase.PHASE_SUBMISSION,
        ]

        with patch("src.orchestrator.engine.load_skill") as mock_load, \
             patch("src.orchestrator.engine.unload_skill") as mock_unload:
            for phase in transitions:
                await engine.transition_phase("task-1", phase)

        # After all transitions, the last loaded skill should be wallet-management
        calls = [c[0][0] for c in mock_load.call_args_list]
        assert "wallet-management" in calls

    @pytest.mark.asyncio
    async def test_unloads_old_skill(self, engine):
        """Transitioning unloads the previous phase's skill."""
        with patch("src.orchestrator.engine.load_skill") as mock_load, \
             patch("src.orchestrator.engine.unload_skill") as mock_unload:
            # First to DISCOVERY (loads bidding-strategy)
            await engine.transition_phase(None, Phase.PHASE_DISCOVERY)
            assert "bidding-strategy" in engine.active_skills

            # Then to RESEARCH (unloads bidding-strategy, loads research)
            await engine.transition_phase(None, Phase.PHASE_RESEARCH)

            mock_unload.assert_called_with("bidding-strategy")
            assert "bidding-strategy" not in engine.active_skills
            assert "research" in engine.active_skills

    @pytest.mark.asyncio
    async def test_invalid_phase_raises_value_error(self, engine):
        """Unknown phase raises ValueError."""
        with patch("src.orchestrator.engine.load_skill"), \
             patch("src.orchestrator.engine.unload_skill"):
            with pytest.raises(ValueError, match="Unknown phase"):
                await engine.transition_phase("task-1", "INVALID_PHASE")

    @pytest.mark.asyncio
    async def test_transition_without_task_id(self, engine):
        """transition_phase with task_id=None only handles skill loading."""
        with patch("src.orchestrator.engine.load_skill") as mock_load:
            await engine.transition_phase(None, Phase.PHASE_DISCOVERY)

        mock_load.assert_called_once_with("bidding-strategy")
        assert "bidding-strategy" in engine.active_skills


# ---------------------------------------------------------------------------
# handle_task_completion
# ---------------------------------------------------------------------------


class TestHandleTaskCompletion:
    """handle_task_completion archives task and resets to discovery."""

    @pytest.mark.asyncio
    async def test_updates_status_to_submitted(self, engine, mock_store):
        """Task status becomes SUBMITTED."""
        await mock_store.add_task("task-done", title="Done", status="IN_PROGRESS")

        with patch("src.orchestrator.engine.load_skill"), \
             patch("src.orchestrator.engine.unload_skill"):
            await engine.handle_task_completion("task-done")

        task = await mock_store.get_task("task-done")
        assert task["status"] == "SUBMITTED"

    @pytest.mark.asyncio
    async def test_transitions_back_to_discovery(self, engine):
        """After completion, orchestrator transitions to DISCOVERY."""
        with patch("src.orchestrator.engine.load_skill") as mock_load:
            await engine.handle_task_completion("any-task")

        # Should have transitioned to DISCOVERY (loads bidding-strategy)
        load_calls = [c[0][0] for c in mock_load.call_args_list]
        assert "bidding-strategy" in load_calls


# ---------------------------------------------------------------------------
# run_discovery_cycle (mocked)
# ---------------------------------------------------------------------------


class TestRunDiscoveryCycle:
    """run_discovery_cycle scans tasks and places bids."""

    @pytest.mark.asyncio
    async def test_evaluates_and_bids_on_good_tasks(self, engine, mock_config):
        """Tasks that match specializations get evaluated and bid on."""
        mock_tasks_api = AsyncMock(return_value=[
            {
                "id": "disc-task-1",
                "title": "Good Task",
                "description": "Build something",
                "category": "backend",
                "price_points": 500,
                "deadline": "2026-05-01",
            }
        ])

        mock_evaluation = {
            "skill_fit": True,
            "confidence": 0.85,
            "recommended_points": 525,
            "approach": "Implement with FastAPI",
        }

        mock_estimate = AsyncMock(return_value=120)

        with patch("src.skills.bidding_strategy.should_evaluate_task", return_value=True), \
             patch("src.skills.bidding_strategy.evaluate_task",
                   return_value=mock_evaluation), \
             patch("src.wallet.client.list_tasks", mock_tasks_api), \
             patch("src.wallet.client.estimate_time", mock_estimate), \
             patch("src.wallet.client.place_bid") as mock_bid:
            await engine.run_discovery_cycle(mock_config)

        mock_bid.assert_called_once_with(
            task_id="disc-task-1",
            price_points=525,
            estimated_minutes=120,
            proposed_approach="Implement with FastAPI",
            config=mock_config,
        )

    @pytest.mark.asyncio
    async def test_skips_tasks_with_low_confidence(self, engine, mock_config):
        """Tasks with confidence <= 0.6 are skipped."""
        mock_tasks_api = AsyncMock(return_value=[{"id": "skip-me"}])

        with patch("src.skills.bidding_strategy.should_evaluate_task", return_value=True), \
             patch("src.skills.bidding_strategy.evaluate_task",
                   return_value={"skill_fit": True, "confidence": 0.5,
                                 "recommended_points": 100, "approach": "x"}), \
             patch("src.wallet.client.list_tasks", mock_tasks_api), \
             patch("src.wallet.client.place_bid") as mock_bid, \
             patch("src.wallet.client.estimate_time"):
            await engine.run_discovery_cycle(mock_config)

        mock_bid.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_tasks_with_skill_fit_false(self, engine, mock_config):
        """Tasks with skill_fit=False are skipped."""
        mock_tasks_api = AsyncMock(return_value=[{"id": "no-fit"}])

        with patch("src.skills.bidding_strategy.should_evaluate_task", return_value=True), \
             patch("src.skills.bidding_strategy.evaluate_task",
                   return_value={"skill_fit": False, "confidence": 0.9,
                                 "recommended_points": 100, "approach": "x"}), \
             patch("src.wallet.client.list_tasks", mock_tasks_api), \
             patch("src.wallet.client.place_bid") as mock_bid, \
             patch("src.wallet.client.estimate_time"):
            await engine.run_discovery_cycle(mock_config)

        mock_bid.assert_not_called()

    @pytest.mark.asyncio
    async def test_stores_evaluated_task_in_sqlite(self, engine, mock_config, mock_store):
        """Successfully bid tasks are stored in the SQLite database."""
        mock_tasks_api = AsyncMock(return_value=[
            {
                "id": "store-task-1",
                "title": "Stored Task",
                "description": "Do something",
                "category": "backend",
                "price_points": 300,
                "deadline": "2026-06-01",
            }
        ])

        mock_evaluation = {
            "skill_fit": True,
            "confidence": 0.8,
            "recommended_points": 300,
            "approach": "Approach",
        }

        with patch("src.skills.bidding_strategy.should_evaluate_task", return_value=True), \
             patch("src.skills.bidding_strategy.evaluate_task",
                   return_value=mock_evaluation), \
             patch("src.wallet.client.list_tasks", mock_tasks_api), \
             patch("src.wallet.client.estimate_time",
                   AsyncMock(return_value=60)), \
             patch("src.wallet.client.place_bid"):
            await engine.run_discovery_cycle(mock_config)

        task = await mock_store.get_task("store-task-1")
        assert task is not None
        assert task["status"] == "BIDDING"
        assert task["title"] == "Stored Task"
