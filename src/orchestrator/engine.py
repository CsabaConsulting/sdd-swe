"""Orchestrator engine — finite state machine for task lifecycle."""

from enum import Enum
from typing import Optional
from datetime import datetime
from src.db.store import AegisStore
from src.skills.loader import load_skill, unload_skill, get_active_skills


class Phase(str, Enum):
    """Task lifecycle phases."""
    PHASE_DISCOVERY = "PHASE_DISCOVERY"
    PHASE_RESEARCH = "PHASE_RESEARCH"
    PHASE_DELIVERY = "PHASE_DELIVERY"
    PHASE_VALIDATION = "PHASE_VALIDATION"
    PHASE_SUBMISSION = "PHASE_SUBMISSION"


# Phase transition map: (from_phase, to_phase) -> skills to load/unload
PHASE_TRANSITIONS = {
    Phase.PHASE_DISCOVERY: {
        "load": "bidding-strategy",
        "unload": None,
    },
    Phase.PHASE_RESEARCH: {
        "load": "research",
        "unload": "bidding-strategy",
    },
    Phase.PHASE_DELIVERY: {
        "load": "code-delivery",
        "unload": "research",
    },
    Phase.PHASE_VALIDATION: {
        "load": "validation",
        "unload": "code-delivery",
    },
    Phase.PHASE_SUBMISSION: {
        "load": "wallet-management",
        "unload": "validation",
    },
}


class OrchestratorEngine:
    """Manages task lifecycle via finite state machine."""

    def __init__(self, store: AegisStore):
        self.store = store
        self.active_skills: set[str] = set()

    async def init(self) -> None:
        """Initialize orchestrator — load initial skill."""
        await self.transition_phase(None, Phase.PHASE_DISCOVERY)

    async def transition_phase(self, task_id: Optional[str], new_phase: Phase) -> None:
        """Transition to a new phase, updating task state and skill loading.

        Args:
            task_id: Task being transitioned (None for initial setup)
            new_phase: Target phase

        Side effects:
            - Updates task in SQLite
            - Unloads old skill
            - Loads new skill
            - Logs transition
        """
        transition_info = PHASE_TRANSITIONS.get(new_phase)
        if not transition_info:
            raise ValueError(f"Unknown phase: {new_phase}")

        # Update task state
        if task_id:
            await self.store.update_task(task_id, phase=new_phase.value)

        # Unload old skill
        skill_to_unload = transition_info["unload"]
        if skill_to_unload and skill_to_unload in self.active_skills:
            await unload_skill(skill_to_unload)
            self.active_skills.discard(skill_to_unload)
            print(f"Skill unloaded: {skill_to_unload}")

        # Load new skill
        skill_to_load = transition_info["load"]
        if skill_to_load and skill_to_load not in self.active_skills:
            await load_skill(skill_to_load)
            self.active_skills.add(skill_to_load)
            print(f"Skill loaded: {skill_to_load} (phase: {new_phase.value})")

    async def run_discovery_cycle(self, config) -> None:
        """Scan /tasks, evaluate tasks, place bids.

        This is the main discovery loop — runs during PHASE_DISCOVERY.

        Args:
            config: Application config for API calls
        """
        from src.skills.bidding_strategy import should_evaluate_task, evaluate_task
        from src.wallet.client import place_bid, estimate_time, list_tasks
        from src.config.loader import AegisConfig

        # Fetch tasks
        tasks = await list_tasks(config)

        for task in tasks:
            if not should_evaluate_task(task):
                continue

            # Evaluate task
            evaluation = await evaluate_task(task, config)

            # If good fit, place bid
            if evaluation["skill_fit"] and evaluation["confidence"] > 0.6:
                estimated_minutes = await estimate_time(task.get("description", ""), config)

                await place_bid(
                    task_id=task["id"],
                    price_points=evaluation["recommended_points"],
                    estimated_minutes=estimated_minutes,
                    proposed_approach=evaluation["approach"],
                    config=config,
                )

                # Store task locally
                await self.store.add_task(
                    task_id=task["id"],
                    title=task.get("title", ""),
                    description=task.get("description", ""),
                    category=task.get("category", ""),
                    points=task.get("price_points", 0),
                    deadline=task.get("deadline", ""),
                    status="BIDDING",
                )

    async def handle_task_completion(self, task_id: str) -> None:
        """Archive completed task, reset to discovery.

        Args:
            task_id: Completed task ID
        """
        await self.store.update_task(task_id, status="SUBMITTED")
        await self.transition_phase(task_id, Phase.PHASE_DISCOVERY)


async def main():
    """Test mode: verify state machine transitions."""
    from src.db.store import AegisStore

    store = AegisStore()
    await store.init_db()

    engine = OrchestratorEngine(store)
    await engine.init()

    # Test transition sequence
    await store.add_task("test-task-1", "Test Task", category="development", points=100, status="BIDDING")

    print("\nTesting phase transitions:")
    await engine.transition_phase("test-task-1", Phase.PHASE_RESEARCH)
    task = await store.get_task("test-task-1")
    print(f"  Phase: {task['phase']}")

    await engine.transition_phase("test-task-1", Phase.PHASE_DELIVERY)
    task = await store.get_task("test-task-1")
    print(f"  Phase: {task['phase']}")

    await engine.transition_phase("test-task-1", Phase.PHASE_VALIDATION)
    task = await store.get_task("test-task-1")
    print(f"  Phase: {task['phase']}")

    await engine.transition_phase("test-task-1", Phase.PHASE_SUBMISSION)
    task = await store.get_task("test-task-1")
    print(f"  Phase: {task['phase']}")

    print(f"\nActive skills: {engine.active_skills}")
    print("\nOrchestrator engine test passed!")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
