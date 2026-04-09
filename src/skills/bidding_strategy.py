"""Bidding strategy — LLM-based task evaluation."""

import asyncio
from typing import TypedDict
from openai import AsyncOpenAI
from src.config.loader import AegisConfig
from src.wallet.vault import vault


class TaskEvaluation(TypedDict):
    """Result from task evaluation."""
    skill_fit: bool
    points_to_effort: float
    confidence: float
    recommended_points: int
    approach: str


def should_evaluate_task(task: dict, specializations: list[str] = None) -> bool:
    """Determine if agent should bid on task.

    Args:
        task: Task dict from /tasks endpoint
        specializations: Optional list of specialization categories

    Returns:
        True if task should be evaluated
    """
    # Filter 1: Only open tasks
    if task.get("status") != "open":
        return False

    # Filter 2: Specialization match (if configured)
    if specializations and task.get("category") not in specializations:
        return False

    return True


def _get_llm_client() -> AsyncOpenAI:
    """Create OpenRouter client."""
    return AsyncOpenAI(
        api_key=vault.load_openrouter_key(),
        base_url="https://openrouter.ai/api/v1"
    )


async def _llm_analyze_complexity(task_description: str, category: str) -> tuple[str, float]:
    """Use LLM to analyze task complexity and estimate effort.

    Args:
        task_description: Full task description
        category: Task category

    Returns:
        (complexity_level, effort_hours) tuple
    """
    client = _get_llm_client()

    prompt = (
        f"Analyze this task for a freelance agent to bid on.\n\n"
        f"Category: {category}\n"
        f"Description: {task_description[:3000]}\n\n"
        f"Respond with JSON containing:\n"
        f'- "complexity": one of "simple", "moderate", "complex", "very_complex"\n'
        f'- "effort_hours": estimated hours as a number\n'
    )

    try:
        response = await client.chat.completions.create(
            model="openai/gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100,
            temperature=0,
        )

        import json
        content = response.choices[0].message.content.strip()
        result = json.loads(content)

        complexity = result.get("complexity", "moderate")
        effort_hours = float(result.get("effort_hours", 4))

        return complexity, effort_hours

    except Exception as e:
        print(f"LLM complexity analysis error: {e}")
        return "moderate", 4.0  # Default


async def evaluate_task(task: dict, config: AegisConfig) -> TaskEvaluation:
    """Evaluate task for bidding using LLM analysis.

    Uses LLM to analyze task complexity, then calculates bid parameters.

    Args:
        task: Task dict from /tasks
        config: Application config

    Returns:
        TaskEvaluation with bid recommendation
    """
    points = task.get("price_points", 100)
    description = task.get("description", "")
    category = task.get("category", "development")

    # LLM analyzes complexity
    complexity, effort_hours = await _llm_analyze_complexity(description, category)

    # Calculate points-to-effort ratio
    points_to_effort = points / max(effort_hours, 0.5)

    # Calculate confidence based on complexity
    complexity_confidence = {
        "simple": 0.95,
        "moderate": 0.80,
        "complex": 0.65,
        "very_complex": 0.50,
    }
    confidence = complexity_confidence.get(complexity, 0.7)

    # Calculate recommended points (adjust based on complexity)
    if complexity == "very_complex":
        recommended_points = int(points * 1.1)  # Premium for hard tasks
    elif complexity == "complex":
        recommended_points = int(points * 1.05)
    else:
        recommended_points = points

    # Generate approach via LLM
    approach = await _llm_generate_approach(description, category, complexity)

    return TaskEvaluation(
        skill_fit=True,
        points_to_effort=points_to_effort,
        confidence=confidence,
        recommended_points=recommended_points,
        approach=approach,
    )


async def _llm_generate_approach(description: str, category: str, complexity: str) -> str:
    """Generate bid approach description via LLM.

    Args:
        description: Task description
        category: Task category
        complexity: Complexity level

    Returns:
        LLM-generated approach description
    """
    client = _get_llm_client()

    prompt = (
        f"Write a brief approach description for this freelance task.\n\n"
        f"Category: {category}\n"
        f"Complexity: {complexity}\n"
        f"Description: {description[:2000]}\n\n"
        f"Write 2-3 sentences describing your approach. Be specific about tools/methods."
    )

    try:
        response = await client.chat.completions.create(
            model="openai/gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150,
            temperature=0.5,
        )

        return response.choices[0].message.content.strip()[:300]

    except Exception as e:
        print(f"LLM approach generation error: {e}")
        return f"Implement {category} solution addressing all requirements with appropriate testing."
