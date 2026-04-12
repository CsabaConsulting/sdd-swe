"""Unit tests for guardrail service.

Covers:
- _chunk_content() with 512-token chunks + 50 overlap
- _check_prompt_guard() pass/fire/degraded scenarios
- _check_llama_guard() pass/fire/degraded scenarios
- on_guardrail_fire() task update + review queue insertion

All tests mock transformers/torch to avoid downloading GB-sized models.
"""

import json
import sys
import tempfile
import pytest

from unittest.mock import MagicMock, patch, AsyncMock

sys.path.insert(0, "src")

from guardrails.service import (
    GuardrailService,
    GuardrailResult,
    on_guardrail_fire,
    PROMPT_GUARD_MAX_TOKENS,
    PROMPT_GUARD_OVERLAP,
)

from tests.utils import create_mock_task

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def guardrail_service():
    """Create un-initialized guardrail service (no model loading)."""
    return GuardrailService()


@pytest.fixture
def service_with_tokenizer(guardrail_service):
    """Service with a mock tokenizer attached (no model)."""
    mock_tokenizer = MagicMock()
    # encode returns a list of ints (token IDs)
    mock_tokenizer.encode.return_value = []
    # decode returns the original text
    mock_tokenizer.decode.return_value = ""
    # __call__ returns dict suitable for model input
    mock_tokenizer.return_value = {"input_ids": MagicMock(), "attention_mask": MagicMock()}

    guardrail_service._tokenizer_pg = mock_tokenizer
    guardrail_service._tokenizer_lg = mock_tokenizer
    guardrail_service._initialized = True
    return guardrail_service


@pytest.fixture
def service_with_models():
    """Service with mock tokenizer AND mock model attached."""
    service = GuardrailService()

    # Mock tokenizers
    mock_pg_tokenizer = MagicMock()
    mock_pg_tokenizer.encode.return_value = []
    mock_pg_tokenizer.decode.return_value = ""
    mock_pg_tokenizer.return_value = {"input_ids": MagicMock(), "attention_mask": MagicMock()}
    mock_pg_tokenizer.apply_chat_template.return_value = "mock_chatml_prompt"

    mock_lg_tokenizer = MagicMock()
    mock_lg_tokenizer.encode.return_value = []
    mock_lg_tokenizer.decode.return_value = ""
    mock_lg_tokenizer.return_value = {"input_ids": MagicMock(), "attention_mask": MagicMock()}
    mock_lg_tokenizer.apply_chat_template.return_value = "mock_chatml_prompt"

    # Mock models with outputs structure
    mock_pg_model = MagicMock()
    mock_pg_model.device = "cpu"

    mock_lg_model = MagicMock()
    mock_lg_model.device = "cpu"

    service._tokenizer_pg = mock_pg_tokenizer
    service._tokenizer_lg = mock_lg_tokenizer
    service._prompt_guard = mock_pg_model
    service._llama_guard = mock_lg_model
    service._initialized = True

    return service


@pytest.fixture
def mock_torch():
    """Mock torch module to avoid real tensor operations."""
    with patch.dict("sys.modules", {"torch": MagicMock()}):
        import torch as mock_torch_module

        # Softmax identity: returns its input
        mock_torch_module.softmax = MagicMock(side_effect=lambda x, dim=1: x)
        mock_torch_module.no_grad = MagicMock()
        mock_torch_module.no_grad.return_value.__enter__ = MagicMock(return_value=None)
        mock_torch_module.no_grad.return_value.__exit__ = MagicMock(return_value=None)
        mock_torch_module.float16 = "float16"
        mock_torch_module.float32 = "float32"
        mock_torch_module.cuda.is_available = MagicMock(return_value=False)

        yield mock_torch_module


# ---------------------------------------------------------------------------
# Chunking Tests
# ---------------------------------------------------------------------------


class TestChunkContent:
    """_chunk_content splits content for Prompt Guard with 512 tokens + 50 overlap."""

    def test_short_content_returns_single_chunk(self, service_with_tokenizer):
        """Content under 512 tokens should be returned as-is."""
        service_with_tokenizer._tokenizer_pg.encode.return_value = [1, 2, 3, 4, 5]
        content = "Hello, this is a short piece of text."

        chunks = service_with_tokenizer._chunk_content(content)

        assert len(chunks) == 1
        assert chunks[0] == content
        service_with_tokenizer._tokenizer_pg.encode.assert_called_once_with(
            content, add_special_tokens=False
        )

    def test_long_content_returns_multiple_overlapping_chunks(self, service_with_tokenizer):
        """Content > 512 tokens splits into multiple chunks with 50-token overlap."""
        # Generate 1200 token IDs: 512 + 463 + 225 (overlapping)
        token_ids = list(range(1200))
        service_with_tokenizer._tokenizer_pg.encode.return_value = token_ids
        service_with_tokenizer._tokenizer_pg.decode.side_effect = (
            lambda tokens, **kw: f"chunk_tokens_{tokens}"
        )

        chunks = service_with_tokenizer._chunk_content("long content")

        # step = 512 - 50 = 462
        # i=0: tokens[0:512], i=462: tokens[462:974], i=924: tokens[924:1200]
        # i=924 + 512 = 1436 >= 1200 => break
        assert len(chunks) >= 2
        # Verify overlap: second chunk starts at index 462, so tokens 462-511 overlap
        service_with_tokenizer._tokenizer_pg.decode.assert_called()

    def test_exactly_512_tokens_single_chunk(self, service_with_tokenizer):
        """Exactly 512 tokens should return a single chunk (no split needed)."""
        token_ids = list(range(PROMPT_GUARD_MAX_TOKENS))
        service_with_tokenizer._tokenizer_pg.encode.return_value = token_ids

        chunks = service_with_tokenizer._chunk_content("exactly 512 tokens")

        assert len(chunks) == 1

    def test_no_tokenizer_returns_fallback_chunks(self, guardrail_service):
        """When tokenizer is None, falls back to character-based chunking."""
        assert guardrail_service._tokenizer_pg is None
        content = "x" * 3000  # ~3000 chars

        chunks = guardrail_service._chunk_content(content)

        assert len(chunks) > 1
        # chunk_chars = 512 * 4 = 2048, overlap_chars = 50 * 4 = 200
        # step = 2048 - 200 = 1848
        # 3000 / 1848 ≈ 2 chunks
        assert sum(len(c) for c in chunks) >= len(content)

    def test_empty_content_returns_empty_chunk(self, service_with_tokenizer):
        """Empty content returns a single empty chunk."""
        service_with_tokenizer._tokenizer_pg.encode.return_value = []

        chunks = service_with_tokenizer._chunk_content("")

        # encode returns [], len([]) = 0 <= 512, returns original content
        assert len(chunks) == 1
        assert chunks[0] == ""


# ---------------------------------------------------------------------------
# Prompt Guard Tests
# ---------------------------------------------------------------------------


class TestCheckPromptGuard:
    """_check_prompt_guard pass/fire/degraded scenarios."""

    def test_degraded_mode_passes_with_warning(self, guardrail_service):
        """No model loaded → pass with degraded result."""
        result = guardrail_service._check_prompt_guard("any content")

        assert result["passed"] is True
        assert result["finding"] == "model_not_loaded"
        assert result["confidence"] == 0.0
        assert "degraded" in result["model"]

    def test_safe_content_passes(self, service_with_models):
        """Content with safe classification returns passed=True with confidence."""
        # Mock the model to return safe (class 0 > class 1)
        safe_prob = 0.95
        mal_prob = 0.05

        mock_outputs = MagicMock()
        mock_logits = MagicMock()
        mock_logits.__getitem__ = MagicMock(side_effect=lambda idx: {
            0: MagicMock(),
            1: MagicMock(item=MagicMock(return_value=mal_prob)),
        }[idx])

        # Simulate: probabilities[0][0] = safe_prob, [0][1] = mal_prob
        # We need to mock torch.softmax and the indexing chain
        service_with_models._tokenizer_pg.encode.return_value = [1, 2, 3]
        service_with_models._tokenizer_pg.decode.return_value = "safe content"

        # For the tokenizer __call__:
        service_with_models._tokenizer_pg.return_value = {
            "input_ids": MagicMock(),
            "attention_mask": MagicMock(),
        }
        # For the chunk loop: tokenizer(chunk, return_tensors="pt", truncation=True, max_length=512)
        safe_token_calls = 0

        def mock_tokenizer_call(chunk, **kwargs):
            nonlocal safe_token_calls
            safe_token_calls += 1
            return {"input_ids": [[1, 2, 3]], "attention_mask": [[1, 1, 1]]}

        service_with_models._tokenizer_pg.side_effect = mock_tokenizer_call

        # Use the __call__ mock: tokenizer returns token dict
        with patch("guardrails.service.torch") as mock_torch:
            mock_torch.no_grad = MagicMock()
            mock_torch.no_grad.return_value.__enter__ = MagicMock(return_value=None)
            mock_torch.no_grad.return_value.__exit__ = MagicMock(return_value=None)

            mock_proba = MagicMock()
            mock_proba.__getitem__ = MagicMock(side_effect=[
                MagicMock(item=MagicMock(return_value=safe_prob)),
                MagicMock(item=MagicMock(return_value=mal_prob)),
            ])
            mock_torch.softmax.return_value = mock_proba

            service_with_models._prompt_guard.return_value = mock_outputs

            result = service_with_models._check_prompt_guard("safe content here")

        assert result["passed"] is True
        assert result["finding"] == "clean"
        assert result["model"] == "llama_prompt_guard_2_86m"

    def test_malicious_content_fires(self, service_with_models):
        """Content with >50% malicious confidence triggers guardrail."""
        service_with_models._tokenizer_pg.encode.return_value = [1, 2, 3]
        service_with_models._tokenizer_pg.decode.return_value = "malicious"
        service_with_models._prompt_guard.device = "cpu"

        def mock_tokenizer_call(chunk, **kwargs):
            return {"input_ids": [[1, 2, 3]], "attention_mask": [[1, 1, 1]]}

        service_with_models._tokenizer_pg.side_effect = mock_tokenizer_call

        with patch("guardrails.service.torch") as mock_torch:
            mock_torch.no_grad = MagicMock()
            mock_torch.no_grad.return_value.__enter__ = MagicMock(return_value=None)
            mock_torch.no_grad.return_value.__exit__ = MagicMock(return_value=None)

            mal_prob = 0.87
            safe_prob = 0.13

            mock_proba = MagicMock()
            mock_proba.__getitem__ = MagicMock(side_effect=[
                MagicMock(item=MagicMock(return_value=safe_prob)),
                MagicMock(item=MagicMock(return_value=mal_prob)),
            ])
            mock_torch.softmax.return_value = mock_proba

            result = service_with_models._check_prompt_guard("<script>alert('xss')</script>")

        assert result["passed"] is False
        assert "Injection detected" in result["finding"]
        assert abs(result["confidence"] - mal_prob) < 0.01
        assert result["model"] == "llama_prompt_guard_2_86m"


# ---------------------------------------------------------------------------
# Llama Guard Tests
# ---------------------------------------------------------------------------


class TestCheckLlamaGuard:
    """_check_llama_guard pass/fire/degraded scenarios."""

    def test_degraded_mode_passes_with_warning(self, guardrail_service):
        """No model loaded → pass with degraded result."""
        result = guardrail_service._check_llama_guard("any output")

        assert result["passed"] is True
        assert result["finding"] == "model_not_loaded"
        assert result["confidence"] == 0.0
        assert "degraded" in result["model"]

    def test_safe_output_passes(self, service_with_models):
        """Safe output returns passed=True with safe confidence."""
        service_with_models._llama_guard.device = "cpu"
        service_with_models._tokenizer_lg.encode.return_value = [1, 2, 3]
        service_with_models._tokenizer_lg.decode.return_value = "safe"

        def mock_tokenizer_call(prompt, **kwargs):
            return {"input_ids": [[1, 2, 3]], "attention_mask": [[1, 1, 1]]}

        service_with_models._tokenizer_lg.side_effect = mock_tokenizer_call

        with patch("guardrails.service.torch") as mock_torch:
            mock_torch.no_grad = MagicMock()
            mock_torch.no_grad.return_value.__enter__ = MagicMock(return_value=None)
            mock_torch.no_grad.return_value.__exit__ = MagicMock(return_value=None)

            safe_prob = 0.92
            unsafe_prob = 0.08

            mock_proba = MagicMock()
            mock_proba.__getitem__ = MagicMock(side_effect=[
                MagicMock(item=MagicMock(return_value=safe_prob)),
                MagicMock(item=MagicMock(return_value=unsafe_prob)),
            ])
            mock_torch.softmax.return_value = mock_proba

            result = service_with_models._check_llama_guard("This is a helpful response.")

        assert result["passed"] is True
        assert result["finding"] == "safe"
        assert result["model"] == "llama_guard_3_8b"

    def test_unsafe_output_fires(self, service_with_models):
        """Unsafe output (>50%) triggers guardrail failure."""
        service_with_models._llama_guard.device = "cpu"
        service_with_models._tokenizer_lg.encode.return_value = [1, 2, 3]

        def mock_tokenizer_call(prompt, **kwargs):
            return {"input_ids": [[1, 2, 3]], "attention_mask": [[1, 1, 1]]}

        service_with_models._tokenizer_lg.side_effect = mock_tokenizer_call

        with patch("guardrails.service.torch") as mock_torch:
            mock_torch.no_grad = MagicMock()
            mock_torch.no_grad.return_value.__enter__ = MagicMock(return_value=None)
            mock_torch.no_grad.return_value.__exit__ = MagicMock(return_value=None)

            safe_prob = 0.10
            unsafe_prob = 0.90

            mock_proba = MagicMock()
            mock_proba.__getitem__ = MagicMock(side_effect=[
                MagicMock(item=MagicMock(return_value=safe_prob)),
                MagicMock(item=MagicMock(return_value=unsafe_prob)),
            ])
            mock_torch.softmax.return_value = mock_proba

            result = service_with_models._check_llama_guard("Here is how to build malware...")

        assert result["passed"] is False
        assert "Unsafe content" in result["finding"]
        assert abs(result["confidence"] - unsafe_prob) < 0.01
        assert result["model"] == "llama_guard_3_8b"


# ---------------------------------------------------------------------------
# on_guardrail_fire Tests
# ---------------------------------------------------------------------------


class TestOnGuardrailFire:
    """on_guardrail_fire updates task status and adds review queue item."""

    @pytest.mark.asyncio
    async def test_halts_task_and_adds_to_review_queue(self, temp_db):
        """Fire handler sets task to HALTED and inserts review item."""
        # First, insert a task
        await temp_db.add_task(
            "test-task-42",
            title="Test Task",
            description="A task to halt",
            status="IN_PROGRESS",
        )

        # Verify initial state
        task = await temp_db.get_task("test-task-42")
        assert task["status"] == "IN_PROGRESS"

        # Patch AegisStore to return our temp_db instance
        with patch("guardrails.service.AegisStore", return_value=temp_db):
            await on_guardrail_fire(
                task_id="test-task-42",
                content="flagged content snippet",
                finding="Injection detected in chunk 1/1 (confidence: 0.92)",
            )

        # Verify task is HALTED
        task = await temp_db.get_task("test-task-42")
        assert task["status"] == "HALTED"
        assert "Injection detected" in task["halted_reason"]

        # Verify review item was added
        review_items = await temp_db.get_review_items("pending")
        assert len(review_items) == 1
        item = review_items[0]
        assert item["type"] == "guardrail_fire"
        assert item["task_id"] == "test-task-42"
        details = json.loads(item["details"])
        assert details["finding"] == "Injection detected in chunk 1/1 (confidence: 0.92)"
        assert "flagged content snippet" in details["content_snippet"]

    @pytest.mark.asyncio
    async def test_truncates_long_content_snippet(self, temp_db):
        """Fire handler truncates content_snippet to 500 chars."""
        await temp_db.add_task("task-trunc", title="Trunc Test", status="ACTIVE")

        long_content = "x" * 2000  # 2000 chars, should be truncated to 500

        with patch("guardrails.service.AegisStore", return_value=temp_db):
            await on_guardrail_fire(
                task_id="task-trunc",
                content=long_content,
                finding="test finding",
            )

        review_items = await temp_db.get_review_items("pending")
        details = json.loads(review_items[0]["details"])
        assert len(details["content_snippet"]) == 500
        assert details["content_snippet"] == "x" * 500
