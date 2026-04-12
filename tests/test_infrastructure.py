"""Smoke tests: verify test infrastructure and fixtures are wired correctly."""

import os
import pytest

from tests.utils import (
    create_mock_task,
    assert_task_status,
    assert_task_phase,
    parse_llm_eval_response,
    json_contains,
)


class TestFixtures:
    """Verify that shared fixtures from conftest.py are accessible."""

    def test_mock_config_returns_test_values(self, mock_config):
        assert mock_config.upmoltwork_api_key.startswith("test_key_")
        assert mock_config.openrouter_api_key.startswith("test_key_")
        assert mock_config.imap_host == "imap.test.com"
        assert mock_config.validation_confidence_threshold == 0.8

    def test_mock_config_low_threshold(self, mock_config_low_threshold):
        assert mock_config_low_threshold.validation_confidence_threshold == 0.5
        assert "web-development" in mock_config_low_threshold.specializations

    def test_mock_api_client_has_required_methods(self, mock_api_client):
        assert callable(getattr(mock_api_client, "get_balance", None))
        assert callable(getattr(mock_api_client, "place_bid", None))
        assert callable(getattr(mock_api_client, "submit_result", None))
        assert callable(getattr(mock_api_client, "list_tasks", None))
        assert callable(getattr(mock_api_client, "get_task", None))

    async def test_mock_api_client_returns_tasks(self, mock_api_client):
        tasks = await mock_api_client.list_tasks()
        assert len(tasks) == 3
        assert tasks[0]["id"] == "task-001"

    async def test_mock_api_client_place_bid(self, mock_api_client):
        result = await mock_api_client.place_bid(
            task_id="task-001",
            price_points=500,
            estimated_minutes=120,
            proposed_approach="Build it",
        )
        assert result.status == "placed"
        assert result.price_points == 500

    async def test_mock_api_client_submit_result(self, mock_api_client):
        result = await mock_api_client.submit_result(task_id="task-001")
        assert result.status == "submitted"

    async def test_mock_api_client_get_balance(self, mock_api_client):
        result = await mock_api_client.get_balance()
        assert result.balance_points == 10000.0
        assert result.balance_usdc == 50.0

    def test_mock_llm_client_returns_default(self, mock_llm_client):
        assert mock_llm_client.default_response == "PASS"

    def test_mock_llm_client_detailed(self, mock_llm_client_detailed):
        assert "Score: 0.92" in mock_llm_client_detailed.default_response


class TestTempDB:
    """Verify temporary database fixture creates and cleans up."""

    async def test_temp_db_is_initialised(self, temp_db):
        """Confirm the temp DB has the expected tables."""
        import aiosqlite
        async with aiosqlite.connect(temp_db.db_path) as db:
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            tables = {row[0] for row in await cursor.fetchall()}
        assert "tasks" in tables
        assert "skills" in tables
        assert "review_queue" in tables
        assert "command_log" in tables

    async def test_temp_db_accepts_writes(self, temp_db):
        await temp_db.add_task("t1", "Smoke Task", status="DISCOVERED")
        task = await temp_db.get_task("t1")
        assert task is not None
        assert task["title"] == "Smoke Task"

    async def test_temp_db_is_fresh_per_test(self, temp_db):
        """Each test gets a clean DB — no leftover rows."""
        tasks = await temp_db.get_tasks_by_status("DISCOVERED")
        assert len(tasks) == 0


class TestUtils:
    """Verify utility helper functions."""

    def test_create_mock_task_defaults(self):
        task = create_mock_task()
        assert task["id"] == "test-task-001"
        assert task["status"] == "DISCOVERED"
        assert task["points"] == 100
        assert isinstance(task["acceptance_criteria"], list)

    def test_create_mock_task_custom(self):
        task = create_mock_task(
            task_id="custom-1",
            status="BIDDING",
            points=500,
        )
        assert task["id"] == "custom-1"
        assert task["status"] == "BIDDING"
        assert task["points"] == 500

    def test_assert_task_status_passes(self):
        task = create_mock_task(status="COMPLETED")
        assert_task_status(task, "COMPLETED")

    def test_assert_task_status_fails(self):
        task = create_mock_task(status="DISCOVERED")
        with pytest.raises(AssertionError, match="Expected task status 'BIDDING'"):
            assert_task_status(task, "BIDDING")

    def test_assert_task_phase(self):
        task = create_mock_task(phase="PHASE_BIDDING")
        assert_task_phase(task, "PHASE_BIDDING")

    def test_parse_llm_eval_response_pass(self):
        text = "PASS\nScore: 0.95\nGood work."
        result = parse_llm_eval_response(text)
        assert result["verdict"] == "PASS"
        assert result["score"] == 0.95

    def test_parse_llm_eval_response_fail(self):
        text = "FAIL\nScore: 0.3\nMissing key feature."
        result = parse_llm_eval_response(text)
        assert result["verdict"] == "FAIL"
        assert result["score"] == 0.3

    def test_json_contains(self):
        data = {"a": 1, "b": 2, "c": 3}
        assert json_contains(data, {"a": 1})
        assert json_contains(data, {"a": 1, "b": 2})
