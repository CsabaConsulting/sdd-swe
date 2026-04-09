"""SQLite store for Aegis state persistence."""

import asyncio
import aiosqlite
from typing import Optional
from datetime import datetime
import json


class AegisStore:
    """Async SQLite interface for tasks, skills, review queue, and command log."""

    def __init__(self, db_path: str = "aegis.db"):
        self.db_path = db_path

    async def init_db(self):
        """Create tables and indexes if they don't exist."""
        async with aiosqlite.connect(self.db_path) as db:
            # tasks table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT,
                    acceptance_criteria TEXT,
                    category TEXT,
                    points INTEGER,
                    deadline TIMESTAMP,
                    status TEXT NOT NULL,
                    phase TEXT,
                    price_points_bid INTEGER,
                    estimated_minutes INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP,
                    deliverable_content TEXT,
                    validation_iterations INTEGER DEFAULT 0,
                    validation_feedback TEXT,
                    halted_reason TEXT,
                    metadata TEXT
                )
            """)

            # skills table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS skills (
                    name TEXT PRIMARY KEY,
                    source TEXT,
                    description TEXT,
                    phase TEXT,
                    verification_status TEXT,
                    checksum TEXT,
                    vetting_result TEXT,
                    sandbox_log TEXT,
                    last_loaded_at TIMESTAMP,
                    tasks_completed INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # review_queue table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS review_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    type TEXT NOT NULL,
                    task_id TEXT,
                    skill_name TEXT,
                    details TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    resolved_at TIMESTAMP
                )
            """)

            # command_log table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS command_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    command TEXT NOT NULL,
                    source TEXT NOT NULL,
                    email_message_id TEXT,
                    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    result TEXT
                )
            """)

            # indexes
            await db.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_tasks_phase ON tasks(phase)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_skills_status ON skills(verification_status)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_review_status ON review_queue(status)")
            await db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_email_commands ON command_log(email_message_id)")

            await db.commit()

    # Task operations
    async def add_task(self, task_id: str, title: str, description: str = None,
                       acceptance_criteria: list = None, category: str = None,
                       points: int = None, deadline: str = None, status: str = "DISCOVERED",
                       metadata: dict = None) -> None:
        """Add a new task to the database."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO tasks (id, title, description, acceptance_criteria, category, points, deadline, status, metadata) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (task_id, title, description, json.dumps(acceptance_criteria) if acceptance_criteria else None,
                 category, points, deadline, status, json.dumps(metadata) if metadata else None)
            )
            await db.commit()

    async def update_task(self, task_id: str, **kwargs) -> None:
        """Update task fields dynamically."""
        if not kwargs:
            return

        fields = []
        values = []

        for key, value in kwargs.items():
            if key == "acceptance_criteria":
                fields.append(f"{key} = ?")
                values.append(json.dumps(value) if value else None)
            elif key == "metadata":
                fields.append(f"{key} = ?")
                values.append(json.dumps(value) if value else None)
            else:
                fields.append(f"{key} = ?")
                values.append(value)

        fields.append("updated_at = ?")
        values.append(datetime.now().isoformat())
        values.append(task_id)

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(f"UPDATE tasks SET {', '.join(fields)} WHERE id = ?", values)
            await db.commit()

    async def get_task(self, task_id: str) -> Optional[dict]:
        """Get a task by ID."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
            row = await cursor.fetchone()
            if not row:
                return None
            return dict(row)

    async def get_tasks_by_status(self, status: str) -> list[dict]:
        """Get all tasks with a specific status."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM tasks WHERE status = ?", (status,))
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    # Skill operations
    async def add_skill(self, name: str, source: str = "built-in", description: str = None,
                        phase: str = None, verification_status: str = "not_verified") -> None:
        """Add a skill to the database."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO skills (name, source, description, phase, verification_status) VALUES (?, ?, ?, ?, ?)",
                (name, source, description, phase, verification_status)
            )
            await db.commit()

    async def update_skill(self, name: str, **kwargs) -> None:
        """Update skill fields dynamically."""
        if not kwargs:
            return

        fields = []
        values = []

        for key, value in kwargs.items():
            if key == "vetting_result" or key == "sandbox_log":
                fields.append(f"{key} = ?")
                values.append(json.dumps(value) if value else None)
            else:
                fields.append(f"{key} = ?")
                values.append(value)

        values.append(name)

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(f"UPDATE skills SET {', '.join(fields)} WHERE name = ?", values)
            await db.commit()

    async def get_skill(self, name: str) -> Optional[dict]:
        """Get a skill by name."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM skills WHERE name = ?", (name,))
            row = await cursor.fetchone()
            if not row:
                return None
            return dict(row)

    async def get_skills_by_verification_status(self, status: str) -> list[dict]:
        """Get skills by verification status."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM skills WHERE verification_status = ?", (status,))
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    # Review queue operations
    async def add_review_item(self, type: str, task_id: str = None, skill_name: str = None,
                               details: dict = None, status: str = "pending") -> int:
        """Add item to review queue. Returns item ID."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "INSERT INTO review_queue (type, task_id, skill_name, details, status) VALUES (?, ?, ?, ?, ?)",
                (type, task_id, skill_name, json.dumps(details) if details else "{}", status)
            )
            await db.commit()
            return cursor.lastrowid

    async def get_review_items(self, status: str = "pending") -> list[dict]:
        """Get review items by status."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM review_queue WHERE status = ? ORDER BY created_at DESC", (status,))
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def resolve_review_item(self, item_id: int, status: str) -> None:
        """Mark review item as resolved."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE review_queue SET status = ?, resolved_at = ? WHERE id = ?",
                (status, datetime.now().isoformat(), item_id)
            )
            await db.commit()

    # Command log operations
    async def log_command(self, command: str, source: str, email_message_id: str = None, result: str = None) -> None:
        """Log a command execution."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO command_log (command, source, email_message_id, result) VALUES (?, ?, ?, ?)",
                (command, source, email_message_id, result)
            )
            await db.commit()

    async def command_exists(self, email_message_id: str) -> bool:
        """Check if an email command has already been processed (idempotency check)."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM command_log WHERE email_message_id = ?", (email_message_id,))
            row = await cursor.fetchone()
            return row[0] > 0


async def main():
    """Test mode: create database and verify tables."""
    import sys

    store = AegisStore()
    await store.init_db()

    print("✓ Database initialized")

    # Test task operations
    await store.add_task("test-1", "Test Task", description="A test task", category="development", points=100, status="DISCOVERED")
    task = await store.get_task("test-1")
    print(f"✓ Task created: {task['title']}")

    await store.update_task("test-1", status="BIDDING", phase="PHASE_DISCOVERY")
    task = await store.get_task("test-1")
    print(f"✓ Task updated: status={task['status']}, phase={task['phase']}")

    # Test skill operations
    await store.add_skill("bidding-strategy", "built-in", "Evaluates tasks", "PHASE_DISCOVERY")
    skill = await store.get_skill("bidding-strategy")
    print(f"✓ Skill created: {skill['name']}")

    # Test review queue
    item_id = await store.add_review_item("guardrail_fire", task_id="test-1", details={"finding": "test"})
    items = await store.get_review_items()
    print(f"✓ Review item added: id={item_id}, count={len(items)}")

    # Test command log
    await store.log_command("/status", "terminal")
    exists = await store.command_exists(None)
    print(f"✓ Command logged")

    print("\nAll tests passed!")


if __name__ == "__main__":
    asyncio.run(main())
