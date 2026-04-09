"""LXC sandbox executor (stub implementation)."""

from typing import TypedDict


class ExecutionResult(TypedDict):
    """Result from sandbox execution."""
    output: str
    exit_code: int


def execute_in_sandbox(code: str, test_command: str, timeout: int = 300) -> ExecutionResult:
    """Run code in isolated LXC container (stub).

    In production: creates LXC container, configures security, executes code.
    For hackathon: returns success stub.

    Args:
        code: Python code to execute
        test_command: Command to run (e.g., "python code.py")
        timeout: Max execution seconds

    Returns:
        ExecutionResult with stdout and exit code
    """
    # Stub: simulate successful execution
    return ExecutionResult(output="Test passed", exit_code=0)
