"""Unit tests for the validation loop (LLM-as-judge).

Covers:
- validate_deliverable() with both criteria + architecture checks
- Iteration tracking (0 -> 3)
- Max iteration behavior (submit after 3 even if quality low)
- Confidence threshold enforcement (0.8 default)
- _llm_check_criteria pass/fail scenarios
- _llm_check_architecture parsing
"""

import json
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.skills.validation import (
    ValidationResult,
    _get_llm_client,
    llm_check_criteria,
    llm_check_architecture,
    validate_deliverable,
)


# ---------------------------------------------------------------------------
# Mock LLM helpers
# ---------------------------------------------------------------------------


def _mock_criteria_client(passed=True, feedback="Looks good"):
    """Create a mock LLM client that returns the given criteria result."""
    response_json = json.dumps({"passed": passed, "feedback": feedback})

    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = response_json

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)
    return mock_client


def _mock_architecture_client(score=0.9):
    """Create a mock LLM client that returns the given architecture score."""
    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = str(score)

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)
    return mock_client


# ---------------------------------------------------------------------------
# llm_check_criteria
# ---------------------------------------------------------------------------


class TestLlmCheckCriteria:
    """llm_check_criteria checks deliverable against acceptance criteria."""

    @pytest.mark.asyncio
    async def test_pass_scenario(self):
        """LLM returns passed=true, feedback parsed correctly."""
        mock_client = _mock_criteria_client(passed=True, feedback="All good")

        with patch("src.skills.validation._get_llm_client", return_value=mock_client):
            passed, feedback = await llm_check_criteria(
                ["Has /users endpoint"],
                "class UsersAPI: ..."
            )

        assert passed is True
        assert feedback == "All good"
        mock_client.chat.completions.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_fail_scenario(self):
        """LLM returns passed=false with issue details."""
        mock_client = _mock_criteria_client(
            passed=False,
            feedback="Missing /users endpoint and auth middleware"
        )

        with patch("src.skills.validation._get_llm_client", return_value=mock_client):
            passed, feedback = await llm_check_criteria(
                ["Has /users endpoint", "Has auth middleware"],
                "def hello(): pass"
            )

        assert passed is False
        assert "Missing /users endpoint" in feedback

    @pytest.mark.asyncio
    async def test_json_decode_fallback(self):
        """Non-JSON response falls back to text parsing."""
        mock_resp = MagicMock()
        mock_resp.choices[0].message.content = "PASS - looks fine"

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)

        with patch("src.skills.validation._get_llm_client", return_value=mock_client):
            passed, feedback = await llm_check_criteria(
                ["something"],
                "some code"
            )

        assert passed is True  # "pass" is in the text
        assert "looks fine" in feedback

    @pytest.mark.asyncio
    async def test_error_returns_false(self):
        """LLM error results in (False, error message)."""
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=RuntimeError("API timeout")
        )

        with patch("src.skills.validation._get_llm_client", return_value=mock_client):
            passed, feedback = await llm_check_criteria(
                ["Has /users"],
                "code"
            )

        assert passed is False
        assert "LLM error" in feedback


# ---------------------------------------------------------------------------
# llm_check_architecture
# ---------------------------------------------------------------------------


class TestLlmCheckArchitecture:
    """llm_check_architecture returns a quality confidence score."""

    @pytest.mark.asyncio
    async def test_parsing_numeric_response(self):
        """Parses a clean numeric score from the LLM."""
        mock_resp = MagicMock()
        mock_resp.choices[0].message.content = "0.85"

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)

        with patch("src.skills.validation._get_llm_client", return_value=mock_client):
            score = await llm_check_architecture("def foo(): return 'structured code'")

        assert abs(score - 0.85) < 0.01

    @pytest.mark.asyncio
    async def test_parsing_score_from_verbose_response(self):
        """Extracts number from a verbose response."""
        mock_resp = MagicMock()
        mock_resp.choices[0].message.content = "I rate this as 0.72 based on structure"

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)

        with patch("src.skills.validation._get_llm_client", return_value=mock_client):
            score = await llm_check_architecture("some code")

        assert abs(score - 0.72) < 0.01

    @pytest.mark.asyncio
    async def test_score_clamped_to_1_0(self):
        """Scores above 1.0 are clamped."""
        mock_resp = MagicMock()
        mock_resp.choices[0].message.content = "1.5"

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)

        with patch("src.skills.validation._get_llm_client", return_value=mock_client):
            score = await llm_check_architecture("amazing code")

        assert score == 1.0

    @pytest.mark.asyncio
    async def test_score_clamped_to_0_0(self):
        """Scores below 0.0 are clamped."""
        mock_resp = MagicMock()
        mock_resp.choices[0].message.content = "-0.3"

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)

        with patch("src.skills.validation._get_llm_client", return_value=mock_client):
            score = await llm_check_architecture("terrible code")

        assert score == 0.0

    @pytest.mark.asyncio
    async def test_default_on_parse_failure(self):
        """Returns 0.5 if no number can be extracted."""
        mock_resp = MagicMock()
        mock_resp.choices[0].message.content = "I cannot rate this"

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)

        with patch("src.skills.validation._get_llm_client", return_value=mock_client):
            score = await llm_check_architecture("???")

        assert score == 0.5

    @pytest.mark.asyncio
    async def test_default_on_api_error(self):
        """Returns 0.5 if the API call fails."""
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=RuntimeError("down")
        )

        with patch("src.skills.validation._get_llm_client", return_value=mock_client):
            score = await llm_check_architecture("code")

        assert score == 0.5


# ---------------------------------------------------------------------------
# validate_deliverable
# ---------------------------------------------------------------------------


class TestValidateDeliverable:
    """validate_deliverable combines criteria + architecture checks."""

    CRITERIA = ["Has /users endpoint", "Has auth middleware"]

    def _setup_validation(self, criteria_passed=True, arch_score=0.9):
        """Set up both LLM mocks for validate_deliverable."""
        criteria_json = json.dumps({
            "passed": criteria_passed,
            "feedback": "criteria feedback" if not criteria_passed else "all good"
        })

        criteria_mock = MagicMock()
        criteria_mock.choices[0].message.content = criteria_json
        criteria_async = AsyncMock(return_value=criteria_mock)

        arch_mock = MagicMock()
        arch_mock.choices[0].message.content = str(arch_score)
        arch_async = AsyncMock(return_value=arch_mock)

        # _get_llm_client is called twice (criteria + architecture)
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=[criteria_mock, arch_mock]
        )

        return patch("src.skills.validation._get_llm_client", return_value=mock_client)

    def test_passes_when_criteria_and_quality_met(self):
        """Both criteria pass and quality >= threshold -> PASS."""
        with self._setup_validation(criteria_passed=True, arch_score=0.92):
            result = validate_deliverable(
                acceptance_criteria=self.CRITERIA,
                deliverable="good code here",
                threshold=0.8,
                iteration_count=0,
                max_iterations=3,
            )

        assert result["passed"] is True
        assert result["quality_confidence"] == pytest.approx(0.92, 0.01)

    def test_fails_when_criteria_fail(self):
        """Failed criteria -> FAIL with feedback."""
        with self._setup_validation(criteria_passed=False, arch_score=0.92):
            result = validate_deliverable(
                acceptance_criteria=self.CRITERIA,
                deliverable="incomplete code",
                threshold=0.8,
                iteration_count=0,
                max_iterations=3,
            )

        assert result["passed"] is False
        assert "Criteria issues" in result["feedback"]

    def test_fails_when_quality_below_threshold(self):
        """Criteria pass but quality < threshold -> FAIL."""
        with self._setup_validation(criteria_passed=True, arch_score=0.6):
            result = validate_deliverable(
                acceptance_criteria=self.CRITERIA,
                deliverable="mediocre code",
                threshold=0.8,
                iteration_count=0,
                max_iterations=3,
            )

        assert result["passed"] is False
        assert result["quality_confidence"] == pytest.approx(0.6, 0.01)

    def test_submits_after_max_iterations_despite_failure(self):
        """When iteration_count >= max_iterations - 1, submits anyway."""
        with self._setup_validation(criteria_passed=False, arch_score=0.5):
            result = validate_deliverable(
                acceptance_criteria=self.CRITERIA,
                deliverable="still broken code",
                threshold=0.8,
                iteration_count=2,  # max_iterations=3, so 2 >= 2
                max_iterations=3,
            )

        assert result["passed"] is True  # submit anyway
        assert "compromised" in result["feedback"].lower()
        assert result["quality_confidence"] == pytest.approx(0.5, 0.01)

    def test_iteration_zero_with_good_code_passes(self):
        """First iteration with good code passes immediately."""
        with self._setup_validation(criteria_passed=True, arch_score=0.95):
            result = validate_deliverable(
                acceptance_criteria=self.CRITERIA,
                deliverable="excellent implementation",
                threshold=0.8,
                iteration_count=0,
                max_iterations=3,
            )

        assert result["passed"] is True
        assert "Validation passed" in result["feedback"]

    def test_custom_threshold_enforcement(self):
        """Custom threshold (e.g., 0.5) allows lower quality to pass."""
        with self._setup_validation(criteria_passed=True, arch_score=0.6):
            result = validate_deliverable(
                acceptance_criteria=self.CRITERIA,
                deliverable="acceptable code",
                threshold=0.5,  # lower threshold
                iteration_count=0,
                max_iterations=3,
            )

        assert result["passed"] is True

    def test_threshold_exactly_at_boundary(self):
        """Quality exactly at threshold passes."""
        with self._setup_validation(criteria_passed=True, arch_score=0.8):
            result = validate_deliverable(
                acceptance_criteria=self.CRITERIA,
                deliverable="borderline code",
                threshold=0.8,
                iteration_count=0,
                max_iterations=3,
            )

        assert result["passed"] is True

    def test_feedback_contains_iteration_info_on_failure(self):
        """Failure feedback includes threshold and confidence details."""
        with self._setup_validation(criteria_passed=True, arch_score=0.6):
            result = validate_deliverable(
                acceptance_criteria=self.CRITERIA,
                deliverable="low quality code",
                threshold=0.8,
                iteration_count=1,
                max_iterations=3,
            )

        assert result["passed"] is False
        assert "0.80" in result["feedback"]  # threshold shown

    def test_max_iterations_boundary_submits_with_compromise_note(self):
        """At iteration_count == max_iterations - 1, submit with compromise note."""
        with self._setup_validation(criteria_passed=False, arch_score=0.4):
            result = validate_deliverable(
                acceptance_criteria=self.CRITERIA,
                deliverable="broken at last attempt",
                threshold=0.8,
                iteration_count=4,  # 4 >= 5-1
                max_iterations=5,
            )

        assert result["passed"] is True
        assert "compromised" in result["feedback"].lower()
        assert "5" in result["feedback"]  # iteration count in message
