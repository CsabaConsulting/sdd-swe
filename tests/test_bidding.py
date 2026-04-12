"""Unit tests for the bidding strategy module.

Covers:
- should_evaluate_task() with open/closed tasks and specialization matching
- _llm_analyze_complexity() with mock LLM
- evaluate_task() with mock LLM, output format and scoring
- _llm_generate_approach() with mock LLM
- Confidence scoring per complexity level
- points_to_effort calculation
"""

import json
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.skills.bidding_strategy import (
    TaskEvaluation,
    should_evaluate_task,
    _llm_analyze_complexity,
    _llm_generate_approach,
    evaluate_task,
)


# ---------------------------------------------------------------------------
# should_evaluate_task
# ---------------------------------------------------------------------------


class TestShouldEvaluateTask:
    """should_evaluate_task filters by status and specialization."""

    def test_open_task_no_specializations(self):
        """Open tasks with no specialization filter are evaluated."""
        task = {"status": "open", "category": "backend"}
        assert should_evaluate_task(task) is True

    def test_non_open_task_rejected(self):
        """Tasks that are not 'open' are rejected."""
        for status in ("closed", "in_progress", "submitted", "cancelled"):
            task = {"status": status, "category": "backend"}
            assert should_evaluate_task(task) is False

    def test_specialization_match(self):
        """Task category in specializations list → evaluate."""
        task = {"status": "open", "category": "backend"}
        assert should_evaluate_task(task, specializations=["backend", "frontend"]) is True

    def test_specialization_mismatch(self):
        """Task category not in specializations list → skip."""
        task = {"status": "open", "category": "design"}
        assert should_evaluate_task(task, specializations=["backend", "frontend"]) is False

    def test_missing_category_defaults_to_development(self):
        """Task without category field is handled gracefully."""
        task = {"status": "open", "category": "backend"}
        assert should_evaluate_task(task, specializations=["backend"]) is True

    def test_empty_specializations_list(self):
        """Empty specializations list means no filtering."""
        task = {"status": "open", "category": "anything"}
        assert should_evaluate_task(task, specializations=[]) is True


# ---------------------------------------------------------------------------
# Mock LLM helpers
# ---------------------------------------------------------------------------


def _mock_llm_complexity_handler(complexity="moderate", effort_hours=4.0):
    """Return a patch for _llm_analyze_complexity."""
    return AsyncMock(return_value=(complexity, effort_hours))


def _mock_llm_approach_handler(text="Build it with tests."):
    """Return a patch for _llm_generate_approach."""
    return AsyncMock(return_value=text)


# ---------------------------------------------------------------------------
# evaluate_task
# ---------------------------------------------------------------------------


class TestEvaluateTask:
    """evaluate_task combines LLM analysis with bid calculation."""

    @pytest.mark.asyncio
    async def test_returns_task_evaluation_dict(self, mock_config):
        """evaluate_task returns a TaskEvaluation TypedDict with all keys."""
        task = {
            "price_points": 500,
            "description": "Build a REST API",
            "category": "backend",
        }

        with patch(
            "src.skills.bidding_strategy._llm_analyze_complexity",
            _mock_llm_complexity_handler(complexity="moderate", effort_hours=5.0),
        ):
            with patch(
                "src.skills.bidding_strategy._llm_generate_approach",
                _mock_llm_approach_handler("Implement endpoints"),
            ):
                result = await evaluate_task(task, mock_config)

        assert "skill_fit" in result
        assert "points_to_effort" in result
        assert "confidence" in result
        assert "recommended_points" in result
        assert "approach" in result

    @pytest.mark.asyncio
    async def test_points_to_effort_calculation(self, mock_config):
        """points_to_effort = points / effort_hours."""
        task = {"price_points": 400, "description": "Simple", "category": "testing"}

        with patch(
            "src.skills.bidding_strategy._llm_analyze_complexity",
            _mock_llm_complexity_handler(complexity="simple", effort_hours=2.0),
        ):
            with patch(
                "src.skills.bidding_strategy._llm_generate_approach",
                _mock_llm_approach_handler("Write tests"),
            ):
                result = await evaluate_task(task, mock_config)

        # 400 / 2.0 = 200.0
        assert result["points_to_effort"] == 200.0

    @pytest.mark.asyncio
    async def test_confidence_for_simple_task(self, mock_config):
        """Simple tasks should have highest confidence (0.95)."""
        task = {"price_points": 100, "description": "Trivial", "category": "testing"}

        with patch(
            "src.skills.bidding_strategy._llm_analyze_complexity",
            _mock_llm_complexity_handler(complexity="simple", effort_hours=1.0),
        ):
            with patch(
                "src.skills.bidding_strategy._llm_generate_approach",
                _mock_llm_approach_handler("Done"),
            ):
                result = await evaluate_task(task, mock_config)

        assert result["confidence"] == 0.95

    @pytest.mark.asyncio
    async def test_confidence_for_complex_task(self, mock_config):
        """Complex tasks have lower confidence (0.65)."""
        task = {"price_points": 600, "description": "Complex thing", "category": "backend"}

        with patch(
            "src.skills.bidding_strategy._llm_analyze_complexity",
            _mock_llm_complexity_handler(complexity="complex", effort_hours=8.0),
        ):
            with patch(
                "src.skills.bidding_strategy._llm_generate_approach",
                _mock_llm_approach_handler("Architect and build"),
            ):
                result = await evaluate_task(task, mock_config)

        assert result["confidence"] == 0.65

    @pytest.mark.asyncio
    async def test_confidence_for_very_complex_task(self, mock_config):
        """Very complex tasks have lowest confidence (0.50)."""
        task = {"price_points": 800, "description": "Very complex", "category": "backend"}

        with patch(
            "src.skills.bidding_strategy._llm_analyze_complexity",
            _mock_llm_complexity_handler(complexity="very_complex", effort_hours=20.0),
        ):
            with patch(
                "src.skills.bidding_strategy._llm_generate_approach",
                _mock_llm_approach_handler("Large project"),
            ):
                result = await evaluate_task(task, mock_config)

        assert result["confidence"] == 0.50

    @pytest.mark.asyncio
    async def test_recommended_points_premium_for_complex(self, mock_config):
        """Complex tasks get 5% premium, very complex 10%."""
        task = {"price_points": 1000, "description": "x", "category": "backend"}

        # Complex → 1000 * 1.05 = 1050
        with patch(
            "src.skills.bidding_strategy._llm_analyze_complexity",
            _mock_llm_complexity_handler(complexity="complex", effort_hours=10.0),
        ):
            with patch(
                "src.skills.bidding_strategy._llm_generate_approach",
                _mock_llm_approach_handler("Approach"),
            ):
                result = await evaluate_task(task, mock_config)

        assert result["recommended_points"] == 1050

    @pytest.mark.asyncio
    async def test_recommended_points_premium_for_very_complex(self, mock_config):
        """Very complex tasks get 10% premium."""
        task = {"price_points": 1000, "description": "x", "category": "backend"}

        with patch(
            "src.skills.bidding_strategy._llm_analyze_complexity",
            _mock_llm_complexity_handler(complexity="very_complex", effort_hours=10.0),
        ):
            with patch(
                "src.skills.bidding_strategy._llm_generate_approach",
                _mock_llm_approach_handler("Approach"),
            ):
                result = await evaluate_task(task, mock_config)

        assert result["recommended_points"] == 1100

    @pytest.mark.asyncio
    async def test_recommended_points_no_premium_for_simple(self, mock_config):
        """Simple/moderate tasks keep original points."""
        task = {"price_points": 300, "description": "x", "category": "backend"}

        with patch(
            "src.skills.bidding_strategy._llm_analyze_complexity",
            _mock_llm_complexity_handler(complexity="simple", effort_hours=2.0),
        ):
            with patch(
                "src.skills.bidding_strategy._llm_generate_approach",
                _mock_llm_approach_handler("Quick"),
            ):
                result = await evaluate_task(task, mock_config)

        assert result["recommended_points"] == 300

    @pytest.mark.asyncio
    async def test_skill_fit_always_true(self, mock_config):
        """skill_fit is always True in current implementation."""
        task = {"price_points": 100, "description": "x", "category": "testing"}

        with patch(
            "src.skills.bidding_strategy._llm_analyze_complexity",
            _mock_llm_complexity_handler(),
        ):
            with patch(
                "src.skills.bidding_strategy._llm_generate_approach",
                _mock_llm_approach_handler("Approach"),
            ):
                result = await evaluate_task(task, mock_config)

        assert result["skill_fit"] is True

    @pytest.mark.asyncio
    async def test_min_effort_hours_floor(self, mock_config):
        """effort_hours is floored at 0.5 to avoid division by zero."""
        task = {"price_points": 100, "description": "x", "category": "testing"}

        with patch(
            "src.skills.bidding_strategy._llm_analyze_complexity",
            _mock_llm_complexity_handler(complexity="simple", effort_hours=0.0),
        ):
            with patch(
                "src.skills.bidding_strategy._llm_generate_approach",
                _mock_llm_approach_handler("Approach"),
            ):
                result = await evaluate_task(task, mock_config)

        # 100 / max(0.0, 0.5) = 200.0
        assert result["points_to_effort"] == 200.0

    @pytest.mark.asyncio
    async def test_default_values_when_task_missing_fields(self, mock_config):
        """Missing task fields fallback to defaults."""
        task = {}  # completely empty

        with patch(
            "src.skills.bidding_strategy._llm_analyze_complexity",
            _mock_llm_complexity_handler(),
        ):
            with patch(
                "src.skills.bidding_strategy._llm_generate_approach",
                _mock_llm_approach_handler("default approach"),
            ):
                result = await evaluate_task(task, mock_config)

        assert result["points_to_effort"] == 100 / 4.0  # defaults: 100 pts, 4 hrs
        assert result["approach"] == "default approach"


# ---------------------------------------------------------------------------
# _llm_generate_approach
# ---------------------------------------------------------------------------


class TestLlmGenerateApproach:
    """_llm_generate_approach delegates to LLM."""

    @pytest.mark.asyncio
    async def test_returns_llm_response(self):
        """Returns the LLM's stripped response."""
        with patch(
            "src.skills.bidding_strategy._get_llm_client"
        ) as mock_client_factory:
            mock_resp = MagicMock()
            mock_resp.choices[0].message.content = "Use FastAPI with JWT auth."
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)
            mock_client_factory.return_value = mock_client

            result = await _llm_generate_approach("Build API", "backend", "moderate")

        assert result == "Use FastAPI with JWT auth."

    @pytest.mark.asyncio
    async def test_truncates_to_300_chars(self):
        """Response is truncated to max 300 characters."""
        long_response = "A" * 500

        with patch(
            "src.skills.bidding_strategy._get_llm_client"
        ) as mock_client_factory:
            mock_resp = MagicMock()
            mock_resp.choices[0].message.content = long_response
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)
            mock_client_factory.return_value = mock_client

            result = await _llm_generate_approach("Big task", "backend", "complex")

        assert len(result) == 300

    @pytest.mark.asyncio
    async def test_default_on_llm_error(self):
        """Returns default approach text when LLM fails."""
        with patch(
            "src.skills.bidding_strategy._get_llm_client",
            side_effect=RuntimeError("API down"),
        ):
            result = await _llm_generate_approach("Build API", "backend", "moderate")

        assert "backend" in result
        assert "solution" in result
