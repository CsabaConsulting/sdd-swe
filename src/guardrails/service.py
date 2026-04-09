"""Guardrail service — Prompt Guard + Llama Guard 3 (stub implementation)."""

from typing import TypedDict


class GuardrailResult(TypedDict):
    """Result from guardrail check."""
    passed: bool
    finding: str
    confidence: float


def check_input(content: str) -> GuardrailResult:
    """Run Prompt Guard on inbound content (stub).

    In production: loads Llama Prompt Guard model, screens for injection.
    For hackathon: always passes (model loading deferred).
    """
    # Stub: always pass for now
    return GuardrailResult(passed=True, finding="", confidence=1.0)


def check_output(content: str) -> GuardrailResult:
    """Run Llama Guard 3 on outbound content (stub).

    In production: loads Llama Guard 3 model, deep taxonomy classification.
    For hackathon: always passes (model loading deferred).
    """
    # Stub: always pass for now
    return GuardrailResult(passed=True, finding="", confidence=1.0)


def on_guardrail_fire(task_id: str, content: str, finding: str) -> None:
    """Handle guardrail fire — halt task, alert user (stub).

    In production: updates SQLite, sends email, logs to terminal.
    For hackathon: just logs the event.
    """
    print(f"GUARDRAIL FIRE on task {task_id}: {finding}")
