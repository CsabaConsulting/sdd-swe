"""Shared pytest fixtures for Aegis test suite."""

import os
import tempfile
import shutil
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from src.config.loader import AegisConfig
from src.db.store import AegisStore


# ---------------------------------------------------------------------------
# Mock configuration
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_config() -> AegisConfig:
    """Provide an AegisConfig with test credentials (no real .env needed)."""
    return AegisConfig(
        upmoltwork_api_key="test_key_upmoltwork_abcdef123456",
        openrouter_api_key="test_key_openrouter_xyz789",
        imap_host="imap.test.com",
        imap_user="test-user@test.com",
        imap_pass="test-imap-password-123",
        validation_confidence_threshold=0.8,
        max_validation_iterations=3,
        guardrail_model_path=None,
        specializations=[],
        email_poll_interval_seconds=30,
    )


@pytest.fixture
def mock_config_low_threshold() -> AegisConfig:
    """Config with a lower validation confidence threshold for easier testing."""
    return AegisConfig(
        upmoltwork_api_key="test_key_upmoltwork_abcdef123456",
        openrouter_api_key="test_key_openrouter_xyz789",
        imap_host="imap.test.com",
        imap_user="test-user@test.com",
        imap_pass="test-imap-password-123",
        validation_confidence_threshold=0.5,
        max_validation_iterations=5,
        guardrail_model_path=None,
        specializations=["web-development", "python"],
        email_poll_interval_seconds=10,
    )


# ---------------------------------------------------------------------------
# Temporary database
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def temp_db():
    """Create a temporary SQLite database with initialised tables.

    Yields:
        AegisStore connected to a fresh temp database.

    The temp directory (and database file) are deleted after the test.
    """
    tmp_dir = tempfile.mkdtemp(prefix="aegis_test_")
    db_path = os.path.join(tmp_dir, "aegis_test.db")

    store = AegisStore(db_path=db_path)
    await store.init_db()

    try:
        yield store
    finally:
        # Clean up temp database and directory
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest_asyncio.fixture
async def temp_db_path():
    """Yield just the temporary database path (without AegisStore).

    Useful when the test needs to construct its own store or
    open the database independently.
    """
    tmp_dir = tempfile.mkdtemp(prefix="aegis_test_path_")
    db_path = os.path.join(tmp_dir, "aegis_test.db")

    try:
        yield db_path
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Mock API client (UpMoltWork)
# ---------------------------------------------------------------------------


class MockUpMoltWorkClient:
    """Fake UpMoltWork API client for unit tests.

    Provides the same interface as the real API functions but returns
    deterministic test data without making network calls.
    """

    def __init__(self):
        self.bids: list[dict] = []
        self.submissions: list[dict] = []
        self.tasks: list[dict] = self._default_tasks()
        self._balance = {"balance_points": 10000.0, "balance_usdc": 50.0}

    @staticmethod
    def _default_tasks() -> list[dict]:
        return [
            {
                "id": "task-001",
                "title": "Build a REST API",
                "description": "Create a simple REST API with authentication",
                "acceptance_criteria": ["Has /users endpoint", "Has auth middleware"],
                "category": "backend",
                "points": 500,
                "status": "open",
            },
            {
                "id": "task-002",
                "title": "Write unit tests",
                "description": "Add pytest unit tests for the project",
                "acceptance_criteria": ["Covers 80%+ code"],
                "category": "testing",
                "points": 200,
                "status": "open",
            },
            {
                "id": "task-003",
                "title": "Fix bug in auth module",
                "description": "Token refresh fails intermittently",
                "acceptance_criteria": ["No more 401 on refresh"],
                "category": "bugfix",
                "points": 300,
                "status": "open",
            },
        ]

    async def get_balance(self, config=None):
        from src.wallet.client import BalanceResult
        return BalanceResult(
            balance_points=self._balance["balance_points"],
            balance_usdc=self._balance["balance_usdc"],
        )

    async def place_bid(self, task_id: str, price_points: int,
                        estimated_minutes: int, proposed_approach: str,
                        config=None):
        from src.wallet.client import BidResult
        bid = {
            "id": f"bid-{len(self.bids) + 1:03d}",
            "task_id": task_id,
            "price_points": price_points,
            "estimated_minutes": estimated_minutes,
        }
        self.bids.append(bid)
        return BidResult(
            bid_id=bid["id"],
            status="placed",
            price_points=price_points,
            estimated_minutes=estimated_minutes,
        )

    async def submit_result(self, task_id: str, result_content: str = None,
                             result_url: str = None, notes: str = None,
                             config=None):
        from src.wallet.client import SubmissionResult
        submission = {
            "id": f"sub-{len(self.submissions) + 1:03d}",
            "task_id": task_id,
        }
        self.submissions.append(submission)
        return SubmissionResult(
            submission_id=submission["id"],
            status="submitted",
        )

    async def list_tasks(self, config=None, status: str = "open"):
        return [t for t in self.tasks if t.get("status") == status]

    async def get_task(self, task_id: str, config=None):
        for t in self.tasks:
            if t["id"] == task_id:
                return t
        return None


@pytest.fixture
def mock_api_client() -> MockUpMoltWorkClient:
    """Provide a mock UpMoltWork API client with pre-loaded test data."""
    return MockUpMoltWorkClient()


# ---------------------------------------------------------------------------
# Mock LLM client (OpenRouter via AsyncOpenAI)
# ---------------------------------------------------------------------------


class MockLLMResponse:
    """Simplified mock of an OpenRouter / ChatCompletion response."""

    def __init__(self, content: str):
        self.choices = [
            type("Choice", (), {
                "message": type("Message", (), {"content": content})()
            })()
        ]


class MockLLMClient:
    """Fake OpenRouter / OpenAI AsyncOpenAI client for tests."""

    def __init__(self, default_response: str = "OK"):
        self.default_response = default_response
        self.call_history: list[dict] = []

    @property
    def chat(self):
        chat_obj = MagicMock()
        chat_obj.completions.create = self._create_completion
        return chat_obj

    async def _create_completion(self, **kwargs):
        self.call_history.append(kwargs)
        return MockLLMResponse(self.default_response)

    async def complete(self, prompt: str, **kwargs) -> str:
        """Convenience method matching a simpler interface."""
        self.call_history.append({"prompt": prompt, **kwargs})
        return self.default_response


@pytest.fixture
def mock_llm_client() -> MockLLMClient:
    """Provide a mock LLM client that returns predictable responses."""
    return MockLLMClient(default_response="PASS")


@pytest.fixture
def mock_llm_client_detailed() -> MockLLMClient:
    """Mock LLM client that returns structured evaluation-like text."""
    return MockLLMClient(
        default_response=(
            "PASS\n"
            "Score: 0.92\n"
            "The solution meets all requirements and handles edge cases."
        )
    )


# ---------------------------------------------------------------------------
# Patcher helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def patch_vault_credentials():
    """Patch the global vault singleton to return test keys.

    Use this fixture when code under test calls
    ``vault.load_upmoltwork_key()`` or ``vault.load_openrouter_key()``.
    """
    with (
        patch("src.wallet.vault.vault.load_upmoltwork_key",
              return_value="test_key_upmoltwork_abcdef123456"),
        patch("src.wallet.vault.vault.load_openrouter_key",
              return_value="test_key_openrouter_xyz789"),
    ):
        yield


@pytest.fixture
def patch_httpx_client():
    """Patch httpx.AsyncClient to prevent real HTTP calls in tests."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {}

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response
    mock_client.post.return_value = mock_response

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_client)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=ctx):
        yield mock_client
