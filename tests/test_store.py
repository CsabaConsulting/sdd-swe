"""Unit tests for the SQLite store.

Covers:
- Task CRUD: add_task, update_task, get_task, get_tasks_by_status
- Skill CRUD: add_skill, update_skill, get_skill, get_skills_by_verification_status
- Review queue: add_review_item, get_review_items, resolve_review_item
- Command log: log_command, command_exists (email_message_id uniqueness)
- Status/phase queries with indexes
"""

import json
from datetime import datetime

import aiosqlite
import pytest

from src.db.store import AegisStore, get_store_sync


# ---------------------------------------------------------------------------
# Task CRUD tests
# ---------------------------------------------------------------------------


class TestTaskCRUD:
    """Complete CRUD lifecycle for tasks."""

    @pytest.mark.asyncio
    async def test_add_task_creates_row(self, temp_db):
        """add_task inserts a row retrievable by get_task."""
        await temp_db.add_task(
            "task-001",
            title="Build REST API",
            description="Create endpoints",
            category="backend",
            points=500,
            status="DISCOVERED",
        )

        task = await temp_db.get_task("task-001")
        assert task is not None
        assert task["title"] == "Build REST API"
        assert task["status"] == "DISCOVERED"
        assert task["points"] == 500
        assert task["category"] == "backend"

    @pytest.mark.asyncio
    async def test_add_task_with_acceptance_criteria(self, temp_db):
        """acceptance_criteria stored as JSON string."""
        criteria = ["Has /users endpoint", "Has auth middleware"]
        await temp_db.add_task(
            "task-002",
            title="API",
            acceptance_criteria=criteria,
            status="open",
        )

        task = await temp_db.get_task("task-002")
        parsed = json.loads(task["acceptance_criteria"])
        assert parsed == criteria

    @pytest.mark.asyncio
    async def test_add_task_with_metadata(self, temp_db):
        """metadata serialized to JSON."""
        meta = {"source": "api", "priority": "high"}
        await temp_db.add_task(
            "task-003",
            title="API",
            status="open",
            metadata=meta,
        )

        task = await temp_db.get_task("task-003")
        assert json.loads(task["metadata"]) == meta

    @pytest.mark.asyncio
    async def test_add_task_default_status(self, temp_db):
        """Default status is DISCOVERED."""
        await temp_db.add_task("task-004", title="Default Status Task")

        task = await temp_db.get_task("task-004")
        assert task["status"] == "DISCOVERED"

    @pytest.mark.asyncio
    async def test_get_task_returns_none_for_missing(self, temp_db):
        """get_task returns None for non-existent ID."""
        result = await temp_db.get_task("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_update_task_changes_fields(self, temp_db):
        """update_task modifies specified fields and sets updated_at."""
        await temp_db.add_task("task-010", title="Original", status="DISCOVERED")

        await temp_db.update_task(
            "task-010",
            status="BIDDING",
            phase="PHASE_DISCOVERY",
            price_points_bid=500,
            estimated_minutes=120,
        )

        task = await temp_db.get_task("task-010")
        assert task["status"] == "BIDDING"
        assert task["phase"] == "PHASE_DISCOVERY"
        assert task["price_points_bid"] == 500
        assert task["estimated_minutes"] == 120
        assert task["updated_at"] is not None

    @pytest.mark.asyncio
    async def test_update_task_with_no_kwargs(self, temp_db):
        """update_task with no kwargs is a no-op."""
        await temp_db.add_task("task-011", title="No-op Update", status="DISCOVERED")
        await temp_db.update_task("task-011")  # should not raise

        task = await temp_db.get_task("task-011")
        assert task["status"] == "DISCOVERED"

    @pytest.mark.asyncio
    async def test_update_task_metadata_json_serialized(self, temp_db):
        """metadata dict is serialized to JSON on update."""
        await temp_db.add_task("task-012", title="Meta Update", status="DISCOVERED")

        new_meta = {"deliverable_url": "http://example.com"}
        await temp_db.update_task("task-012", metadata=new_meta)

        task = await temp_db.get_task("task-012")
        assert json.loads(task["metadata"]) == new_meta

    @pytest.mark.asyncio
    async def test_update_task_acceptance_criteria_json(self, temp_db):
        """acceptance_criteria is JSON serialized on update."""
        await temp_db.add_task("task-013", title="Criteria Update", status="open")

        new_criteria = ["Updated criterion 1"]
        await temp_db.update_task("task-013", acceptance_criteria=new_criteria)

        task = await temp_db.get_task("task-013")
        assert json.loads(task["acceptance_criteria"]) == new_criteria

    @pytest.mark.asyncio
    async def test_get_tasks_by_status(self, temp_db):
        """get_tasks_by_status returns all tasks with matching status."""
        await temp_db.add_task("status-task-1", title="A", status="BIDDING")
        await temp_db.add_task("status-task-2", title="B", status="BIDDING")
        await temp_db.add_task("status-task-3", title="C", status="SUBMITTED")

        bidding = await temp_db.get_tasks_by_status("BIDDING")
        assert len(bidding) == 2
        assert all(t["status"] == "BIDDING" for t in bidding)

        submitted = await temp_db.get_tasks_by_status("SUBMITTED")
        assert len(submitted) == 1

    @pytest.mark.asyncio
    async def test_update_validation_fields(self, temp_db):
        """Validation-related fields update correctly."""
        await temp_db.add_task("val-task", title="Validation", status="IN_PROGRESS")

        await temp_db.update_task(
            "val-task",
            validation_iterations=2,
            validation_feedback="Needs improvement",
            deliverable_content="def test(): pass",
        )

        task = await temp_db.get_task("val-task")
        assert task["validation_iterations"] == 2
        assert task["validation_feedback"] == "Needs improvement"
        assert task["deliverable_content"] == "def test(): pass"

    @pytest.mark.asyncio
    async def test_update_halted_reason(self, temp_db):
        """halted_reason can be set via update_task."""
        await temp_db.add_task("halt-task", title="Halted", status="IN_PROGRESS")
        await temp_db.update_task(
            "halt-task",
            status="HALTED",
            halted_reason="Guardrail fire: injection detected"
        )

        task = await temp_db.get_task("halt-task")
        assert task["status"] == "HALTED"
        assert "Guardrail fire" in task["halted_reason"]


# ---------------------------------------------------------------------------
# Skill CRUD tests
# ---------------------------------------------------------------------------


class TestSkillCRUD:
    """CRUD operations for skills."""

    @pytest.mark.asyncio
    async def test_add_skill(self, temp_db):
        """add_skill creates a row retrievable by get_skill."""
        await temp_db.add_skill(
            "bidding-strategy",
            source="built-in",
            description="Evaluates tasks for bidding",
            phase="PHASE_DISCOVERY",
        )

        skill = await temp_db.get_skill("bidding-strategy")
        assert skill is not None
        assert skill["description"] == "Evaluates tasks for bidding"
        assert skill["verification_status"] == "not_verified"

    @pytest.mark.asyncio
    async def test_add_skill_upsert(self, temp_db):
        """add_skill with same name overwrites (INSERT OR REPLACE)."""
        await temp_db.add_skill("research", source="built-in", phase="PHASE_RESEARCH")
        await temp_db.add_skill("research", source="updated", phase="PHASE_RESEARCH")

        skill = await temp_db.get_skill("research")
        assert skill["source"] == "updated"

    @pytest.mark.asyncio
    async def test_get_skill_missing(self, temp_db):
        """get_skill returns None for non-existent skill."""
        result = await temp_db.get_skill("nonexistent-skill")
        assert result is None

    @pytest.mark.asyncio
    async def test_update_skill(self, temp_db):
        """update_skill modifies fields."""
        await temp_db.add_skill("code-delivery", source="built-in")

        await temp_db.update_skill(
            "code-delivery",
            verification_status="verified",
            tasks_completed=5,
        )

        skill = await temp_db.get_skill("code-delivery")
        assert skill["verification_status"] == "verified"
        assert skill["tasks_completed"] == 5

    @pytest.mark.asyncio
    async def test_update_skill_no_kwargs(self, temp_db):
        """update_skill with no kwargs is a no-op."""
        await temp_db.add_skill("noop-skill", source="built-in")
        await temp_db.update_skill("noop-skill")  # should not raise

    @pytest.mark.asyncio
    async def test_get_skills_by_verification_status(self, temp_db):
        """Skills filtered by verification status."""
        await temp_db.add_skill("skill-a", verification_status="verified")
        await temp_db.add_skill("skill-b", verification_status="verified")
        await temp_db.add_skill("skill-c", verification_status="not_verified")

        verified = await temp_db.get_skills_by_verification_status("verified")
        assert len(verified) == 2

        not_verified = await temp_db.get_skills_by_verification_status("not_verified")
        assert len(not_verified) == 1


# ---------------------------------------------------------------------------
# Review queue tests
# ---------------------------------------------------------------------------


class TestReviewQueue:
    """Review queue operations."""

    @pytest.mark.asyncio
    async def test_add_review_item(self, temp_db):
        """add_review_item inserts and returns the item ID."""
        item_id = await temp_db.add_review_item(
            type="guardrail_fire",
            task_id="task-001",
            details={"finding": "Injection detected"},
        )

        assert item_id is not None
        assert item_id > 0

    @pytest.mark.asyncio
    async def test_get_review_items_pending(self, temp_db):
        """get_review_items returns items matching status."""
        await temp_db.add_review_item(
            "guardrail_fire", task_id="t1", status="pending"
        )
        await temp_db.add_review_item(
            "skill_issue", task_id="t2", status="resolved"
        )

        items = await temp_db.get_review_items("pending")
        assert len(items) == 1
        assert items[0]["type"] == "guardrail_fire"

    @pytest.mark.asyncio
    async def test_get_review_items_default_pending(self, temp_db):
        """Default status for get_review_items is 'pending'."""
        await temp_db.add_review_item("type1", status="pending")

        items = await temp_db.get_review_items()
        assert len(items) >= 1

    @pytest.mark.asyncio
    async def test_resolve_review_item(self, temp_db):
        """resolve_review_item updates status and sets resolved_at."""
        item_id = await temp_db.add_review_item(
            "guardrail_fire", task_id="t1", status="pending"
        )

        await temp_db.resolve_review_item(item_id, "resolved")

        items = await temp_db.get_review_items("resolved")
        assert len(items) == 1
        assert items[0]["id"] == item_id
        assert items[0]["resolved_at"] is not None

    @pytest.mark.asyncio
    async def test_review_item_details_json(self, temp_db):
        """Details are stored as JSON and retrievable."""
        details = {
            "finding": "XSS detected",
            "confidence": 0.92,
            "chunk": 1,
        }
        await temp_db.add_review_item(
            "guardrail_fire",
            task_id="t1",
            details=details,
        )

        items = await temp_db.get_review_items("pending")
        parsed = json.loads(items[0]["details"])
        assert parsed["finding"] == "XSS detected"
        assert parsed["confidence"] == 0.92


# ---------------------------------------------------------------------------
# Command log tests
# ---------------------------------------------------------------------------


class TestCommandLog:
    """Command log and idempotency checks."""

    @pytest.mark.asyncio
    async def test_log_command(self, temp_db):
        """log_command inserts a row."""
        await temp_db.log_command(
            "/status",
            source="terminal",
            result="All systems go",
        )

        # Check that ANY command exists (not by email ID)
        async with aiosqlite.connect(temp_db.db_path) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM command_log")
            row = await cursor.fetchone()
            assert row[0] > 0

    @pytest.mark.asyncio
    async def test_command_exists_with_email_id(self, temp_db):
        """command_exists checks by email_message_id."""
        await temp_db.log_command(
            "/approve",
            source="email",
            email_message_id="msg-001",
        )

        assert await temp_db.command_exists("msg-001") is True
        assert await temp_db.command_exists("msg-999") is False

    @pytest.mark.asyncio
    async def test_command_email_id_enforces_uniqueness(self, temp_db):
        """Duplicate email_message_id raises IntegrityError (unique index)."""
        await temp_db.log_command(
            "/approve",
            source="email",
            email_message_id="unique-msg",
        )

        # Second insert with same email_message_id should raise
        with pytest.raises(Exception):  # aiosqlite or sqlite3.IntegrityError
            await temp_db.log_command(
                "/approve",
                source="email",
                email_message_id="unique-msg",
            )

    @pytest.mark.asyncio
    async def test_command_without_email_id(self, temp_db):
        """Commands without email_message_id can be logged multiple times."""
        await temp_db.log_command("/status", source="terminal")
        await temp_db.log_command("/status", source="terminal")
        # No error expected — uniqueness is per email_message_id (NULLs are distinct
        # in SQLite for regular constraints, but the unique index treats them as
        # distinct in most SQLite versions)

    @pytest.mark.asyncio
    async def test_command_exists_returns_false_initially(self, temp_db):
        """command_exists returns False before any command is logged."""
        assert await temp_db.command_exists("nonexistent-id") is False


# ---------------------------------------------------------------------------
# get_store_sync test
# ---------------------------------------------------------------------------


class TestGetStoreSync:
    """get_store_sync helper."""

    def test_returns_store_instance(self, temp_db_path):
        """get_store_sync returns an AegisStore with the correct path."""
        store = get_store_sync(db_path=temp_db_path)
        assert isinstance(store, AegisStore)
        assert store.db_path == temp_db_path
