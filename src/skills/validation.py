"""Validation skill — LLM-as-judge implementation."""

import asyncio
from typing import TypedDict, Optional
from openai import AsyncOpenAI
from src.wallet.vault import vault


class ValidationResult(TypedDict):
    """Result from validation check."""
    passed: bool
    feedback: str
    quality_confidence: float


def _get_llm_client() -> AsyncOpenAI:
    """Create OpenRouter client with credentials from vault."""
    return AsyncOpenAI(
        api_key=vault.load_openrouter_key(),
        base_url="https://openrouter.ai/api/v1"
    )


async def llm_check_criteria(acceptance_criteria: list, deliverable: str) -> tuple[bool, str]:
    """Check if deliverable meets acceptance criteria via LLM.

    Args:
        acceptance_criteria: List of criteria strings from task
        deliverable: Code/content to validate

    Returns:
        (passed, feedback) tuple
    """
    client = _get_llm_client()

    criteria_text = "\n".join(f"- {c}" for c in acceptance_criteria)

    prompt = (
        f"You are validating a code deliverable against acceptance criteria.\n\n"
        f"Acceptance Criteria:\n{criteria_text}\n\n"
        f"Deliverable:\n{deliverable[:5000]}\n\n"
        f"Check each criterion. Does the deliverable meet ALL acceptance criteria?\n"
        f"Respond with JSON: {{\"passed\": true/false, \"feedback\": \"specific issues found or pass message\"}}"
    )

    try:
        response = await client.chat.completions.create(
            model="openai/gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0,
        )

        content = response.choices[0].message.content.strip()

        # Try to parse JSON response
        import json
        try:
            result = json.loads(content)
            return result.get("passed", False), result.get("feedback", content)
        except json.JSONDecodeError:
            # Fallback: parse from text
            passed = "true" in content.lower() or "pass" in content.lower()
            return passed, content[:200]

    except Exception as e:
        return False, f"LLM error during validation: {str(e)}"


async def llm_check_architecture(deliverable: str) -> float:
    """Check architectural quality confidence via LLM.

    Args:
        deliverable: Code/content to evaluate

    Returns:
        Confidence score 0.0-1.0
    """
    client = _get_llm_client()

    prompt = (
        f"You are evaluating code quality.\n\n"
        f"Code:\n{deliverable[:5000]}\n\n"
        f"Rate the architectural quality on a scale of 0.0 to 1.0 where:\n"
        f"- 0.0-0.3: Poor code structure, no best practices\n"
        f"- 0.3-0.6: Basic implementation with some issues\n"
        f"- 0.6-0.8: Good code with minor room for improvement\n"
        f"- 0.8-1.0: Excellent architecture, follows best practices\n\n"
        f"Respond with ONLY a number between 0.0 and 1.0."
    )

    try:
        response = await client.chat.completions.create(
            model="openai/gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=10,
            temperature=0,
        )

        content = response.choices[0].message.content.strip()
        # Extract number from response
        import re
        match = re.search(r'(\d\.?\d*)', content)
        if match:
            score = float(match.group(1))
            return max(0.0, min(1.0, score))
        return 0.5  # Default if parsing fails

    except Exception as e:
        print(f"LLM error during architecture check: {e}")
        return 0.5  # Default on error


def validate_deliverable(
    acceptance_criteria: list,
    deliverable: str,
    threshold: float = 0.8,
    iteration_count: int = 0,
    max_iterations: int = 3,
) -> ValidationResult:
    """Run validation checks with LLM-as-judge.

    Checks both acceptance criteria compliance AND architectural quality.
    If validation fails and iterations remain, returns feedback for revision.
    If iterations exhausted, submits anyway with compromise note.

    Args:
        acceptance_criteria: List of criteria strings
        deliverable: Deliverable content to validate
        threshold: Minimum quality confidence (0.0-1.0)
        iteration_count: Current iteration (0-based)
        max_iterations: Max allowed iterations

    Returns:
        ValidationResult with pass/fail and feedback
    """
    # This needs to be async - wrapper for sync call
    async def _validate():
        # Check 1: Acceptance criteria compliance
        criteria_passed, criteria_feedback = await llm_check_criteria(acceptance_criteria, deliverable)

        # Check 2: Architectural quality
        quality_confidence = await llm_check_architecture(deliverable)

        # Determine pass/fail
        if criteria_passed and quality_confidence >= threshold:
            return ValidationResult(
                passed=True,
                feedback="Validation passed: meets criteria and quality standards",
                quality_confidence=quality_confidence,
            )

        # Check if max iterations reached
        if iteration_count >= max_iterations - 1:
            return ValidationResult(
                passed=True,  # Submit anyway after max iterations
                feedback=f"Quality compromised after {max_iterations} iterations. {criteria_feedback}",
                quality_confidence=quality_confidence,
            )

        # Failed but iterations remain - provide feedback
        return ValidationResult(
            passed=False,
            feedback=f"Criteria issues: {criteria_feedback}. Quality confidence: {quality_confidence:.2f} (threshold: {threshold:.2f})",
            quality_confidence=quality_confidence,
        )

    # Run async validation
    return asyncio.run(_validate())
