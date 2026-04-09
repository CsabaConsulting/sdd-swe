"""Slash command handlers."""

from typing import Optional
from src.db.store import AegisStore
from src.cli.history import CommandHistory


# Global history singleton
history = CommandHistory()


async def cmd_status(store: AegisStore, args: str = None) -> str:
    """Show overall system status."""
    tasks = await store.get_tasks_by_status("BIDDING")
    in_progress = await store.get_tasks_by_status("DELIVERY")
    halted = await store.get_tasks_by_status("HALTED")

    output = f"System Status:\n"
    output += f"  Bidding: {len(tasks)} tasks\n"
    output += f"  In Progress: {len(in_progress)} tasks\n"
    output += f"  Halted: {len(halted)} tasks\n"
    output += f"  Skills loaded: 0 (not running)"

    history.add("/status", output)
    return output


async def cmd_skills(store: AegisStore, args: str = None) -> str:
    """List all available skills."""
    from src.skills.catalog import scan_builtin_skills

    skills = await scan_builtin_skills()
    output = f"Available Skills ({len(skills)}):\n"

    for skill in skills:
        output += f"  - {skill['name']}: {skill.get('description', 'N/A')}\n"

    history.add("/skills", output)
    return output


async def cmd_tasks(store: AegisStore, args: str = None) -> str:
    """Show active tasks."""
    all_statuses = ["DISCOVERED", "BIDDING", "RESEARCH", "DELIVERY", "VALIDATION", "SUBMITTED"]
    output = "Active Tasks:\n"

    for status in all_statuses:
        tasks = await store.get_tasks_by_status(status)
        if tasks:
            output += f"\n{status} ({len(tasks)}):\n"
            for task in tasks[:5]:  # Show first 5
                output += f"  {task['id']}: {task['title'][:50]}\n"

    history.add("/tasks", output)
    return output


async def cmd_review(store: AegisStore, args: str = None) -> str:
    """Show halted tasks awaiting review."""
    items = await store.get_review_items("pending")
    output = f"Review Queue ({len(items)} pending):\n"

    for item in items[:10]:
        output += f"  #{item['id']}: {item['type']} "
        if item.get('task_id'):
            output += f"on task {item['task_id']} "
        if item.get('skill_name'):
            output += f"for skill {item['skill_name']} "
        output += "\n"

    history.add("/review", output)
    return output


async def cmd_balance(store: AegisStore, args: str = None) -> str:
    """Show points and USDC balance."""
    output = "Balance information:\n"
    output += "  Points: N/A (API not connected)\n"
    output += "  USDC: N/A (API not connected)"

    history.add("/balance", output)
    return output


async def cmd_trace(store: AegisStore, args: str = None) -> str:
    """Get Phoenix trace deep link."""
    if not args:
        return "Usage: /trace <trace_id>"

    output = f"Phoenix trace: http://localhost:6006/trace/{args}"
    history.add(f"/trace {args}", output)
    return output


async def cmd_halt(store: AegisStore, args: str = None) -> str:
    """Halt a running task."""
    if not args:
        return "Usage: /halt <task_id>"

    await store.update_task(args, status="HALTED", halted_reason="User requested halt via /halt")
    output = f"Task {args} halted."
    history.add(f"/halt {args}", output)
    return output


async def cmd_config(store: AegisStore, args: str = None) -> str:
    """Show system configuration."""
    output = "System Configuration:\n"
    output += "  LLM: OpenRouter (default model)\n"
    output += "  Guardrails: Prompt Guard + Llama Guard 3\n"
    output += "  Sandbox: LXC containers\n"
    output += "  Email: IMAP polling (60s interval)"

    history.add("/config", output)
    return output


# Command registry
COMMANDS = {
    "/status": cmd_status,
    "/skills": cmd_skills,
    "/tasks": cmd_tasks,
    "/review": cmd_review,
    "/balance": cmd_balance,
    "/trace": cmd_trace,
    "/halt": cmd_halt,
    "/config": cmd_config,
}


async def execute_command(command_str: str, store: AegisStore) -> str:
    """Execute a slash command.

    Args:
        command_str: Full command string (e.g., "/status")
        store: Database store

    Returns:
        Command output string
    """
    parts = command_str.strip().split(maxsplit=1)
    cmd_name = parts[0]
    args = parts[1] if len(parts) > 1 else None

    handler = COMMANDS.get(cmd_name)
    if not handler:
        return f"Unknown command: {cmd_name}\nAvailable: {', '.join(COMMANDS.keys())}"

    return await handler(store, args)
