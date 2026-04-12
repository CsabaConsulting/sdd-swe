"""Guardrail service — Prompt Guard + Llama Guard 3.

Two-stage pipeline:
1. Llama Prompt Guard 2 (86M params) for fast input screening (<512 token chunks)
2. Llama Guard 3 (8B params) for deep outbound content classification

Both models loaded from HuggingFace Hub, cached locally, run in async mode.
Graceful fallback on failures — if models can't load, service logs warnings
but doesn't crash the agent.
"""

import asyncio
import logging
from typing import TypedDict
from pathlib import Path

logger = logging.getLogger(__name__)

# Model IDs
PROMPT_GUARD_MODEL = "meta-llama/Llama-Prompt-Guard-2-86M"
LLAMA_GUARD_MODEL = "meta-llama/Llama-Guard-3-8B"

# Chunking constants for Prompt Guard (512 token limit)
PROMPT_GUARD_MAX_TOKENS = 512
PROMPT_GUARD_OVERLAP = 50  # tokens overlap between chunks


class GuardrailResult(TypedDict):
    """Result from guardrail check."""
    passed: bool
    finding: str
    confidence: float
    model: str  # which model made the decision


class GuardrailService:
    """Manages guardrail models and checks."""

    def __init__(self, model_path: str | None = None):
        self.model_path = Path(model_path) if model_path else None
        self._prompt_guard = None
        self._llama_guard = None
        self._tokenizer_pg = None
        self._tokenizer_lg = None
        self._initialized = False

    async def initialize(self) -> None:
        """Load models asynchronously on first use.

        Models are cached after first load. If model loading fails,
        service continues in degraded mode (always passes with warning).
        """
        if self._initialized:
            return

        try:
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
            import torch

            logger.info("Loading Llama Prompt Guard 2 (86M)...")
            self._tokenizer_pg = AutoTokenizer.from_pretrained(PROMPT_GUARD_MODEL)
            self._prompt_guard = AutoModelForSequenceClassification.from_pretrained(
                PROMPT_GUARD_MODEL,
                torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
            )
            if torch.cuda.is_available():
                self._prompt_guard.to("cuda")
            self._prompt_guard.eval()
            logger.info("✓ Llama Prompt Guard 2 loaded")

            logger.info("Loading Llama Guard 3 (8B)...")
            self._tokenizer_lg = AutoTokenizer.from_pretrained(LLAMA_GUARD_MODEL)
            self._llama_guard = AutoModelForSequenceClassification.from_pretrained(
                LLAMA_GUARD_MODEL,
                torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
            )
            if torch.cuda.is_available():
                self._llama_guard.to("cuda")
            self._llama_guard.eval()
            logger.info("✓ Llama Guard 3 loaded")

            self._initialized = True

        except Exception as e:
            logger.warning(f"Failed to load guardrail models: {e}")
            logger.warning("Guardrail service running in degraded mode (always passes)")
            self._initialized = True  # Mark as initialized to prevent retry storms

    def _chunk_content(self, content: str) -> list[str]:
        """Split content into chunks for Prompt Guard (512 tokens, 50 overlap).

        Uses tokenizer to ensure accurate token counts.
        """
        if not self._tokenizer_pg:
            # Fallback: character-based chunking if tokenizer unavailable
            chunk_chars = PROMPT_GUARD_MAX_TOKENS * 4  # rough estimate
            overlap_chars = PROMPT_GUARD_OVERLAP * 4
            chunks = []
            for i in range(0, len(content), chunk_chars - overlap_chars):
                chunks.append(content[i:i + chunk_chars])
            return chunks

        # Tokenize
        tokens = self._tokenizer_pg.encode(content, add_special_tokens=False)

        if len(tokens) <= PROMPT_GUARD_MAX_TOKENS:
            return [content]

        # Split into overlapping chunks
        chunks = []
        step = PROMPT_GUARD_MAX_TOKENS - PROMPT_GUARD_OVERLAP
        for i in range(0, len(tokens), step):
            chunk_tokens = tokens[i:i + PROMPT_GUARD_MAX_TOKENS]
            chunk_text = self._tokenizer_pg.decode(chunk_tokens, skip_special_tokens=True)
            chunks.append(chunk_text)

            # Stop if we've covered all tokens
            if i + PROMPT_GUARD_MAX_TOKENS >= len(tokens):
                break

        return chunks

    def _check_prompt_guard(self, content: str) -> GuardrailResult:
        """Run Prompt Guard on content with iterative chunking.

        Returns:
            GuardrailResult with passed=False if any chunk triggers
        """
        if not self._prompt_guard or not self._tokenizer_pg:
            # Degraded mode: pass through
            return GuardrailResult(passed=True, finding="model_not_loaded", confidence=0.0, model="prompt_guard_degraded")

        import torch

        chunks = self._chunk_content(content)
        overall_confidence = 0.0

        for i, chunk in enumerate(chunks):
            inputs = self._tokenizer_pg(chunk, return_tensors="pt", truncation=True, max_length=PROMPT_GUARD_MAX_TOKENS)
            if hasattr(self._prompt_guard, 'device'):
                inputs = {k: v.to(self._prompt_guard.device) for k, v in inputs.items()}

            with torch.no_grad():
                outputs = self._prompt_guard(**inputs)
                logits = outputs.logits
                probabilities = torch.softmax(logits, dim=-1)
                # Class 0 = safe, Class 1 = malicious
                malicious_prob = probabilities[0][1].item()
                safe_prob = probabilities[0][0].item()

            if malicious_prob > 0.5:
                return GuardrailResult(
                    passed=False,
                    finding=f"Injection detected in chunk {i+1}/{len(chunks)} (confidence: {malicious_prob:.2f})",
                    confidence=malicious_prob,
                    model="llama_prompt_guard_2_86m"
                )

            overall_confidence = max(overall_confidence, safe_prob)

        return GuardrailResult(
            passed=True,
            finding="clean",
            confidence=overall_confidence,
            model="llama_prompt_guard_2_86m"
        )

    def _check_llama_guard(self, content: str) -> GuardrailResult:
        """Run Llama Guard 3 on content.

        Llama Guard uses ChatML-style prompting to classify content
        against MLCommons taxonomy categories.
        """
        if not self._llama_guard or not self._tokenizer_lg:
            # Degraded mode: pass through
            return GuardrailResult(passed=True, finding="model_not_loaded", confidence=0.0, model="llama_guard_degraded")

        import torch

        # Llama Guard 3 expects a specific prompt format
        # See: https://huggingface.co/meta-llama/Llama-Guard-3-8B
        chat = [{"role": "user", "content": content}]
        prompt = self._tokenizer_lg.apply_chat_template(chat, tokenize=False, add_generation_prompt=True)

        inputs = self._tokenizer_lg(prompt, return_tensors="pt", truncation=True, max_length=131072)
        if hasattr(self._llama_guard, 'device'):
            inputs = {k: v.to(self._llama_guard.device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = self._llama_guard(**inputs)
            logits = outputs.logits
            probabilities = torch.softmax(logits, dim=-1)
            # Class 0 = safe, Class 1 = unsafe
            unsafe_prob = probabilities[0][1].item()
            safe_prob = probabilities[0][0].item()

        if unsafe_prob > 0.5:
            return GuardrailResult(
                passed=False,
                finding=f"Unsafe content detected (confidence: {unsafe_prob:.2f})",
                confidence=unsafe_prob,
                model="llama_guard_3_8b"
            )

        return GuardrailResult(
            passed=True,
            finding="safe",
            confidence=safe_prob,
            model="llama_guard_3_8b"
        )


# Global service instance (singleton)
_service = GuardrailService()


async def initialize_guardrails(model_path: str | None = None) -> None:
    """Initialize guardrail service on startup.

    Call this during app initialization to preload models.
    """
    global _service
    if model_path:
        _service = GuardrailService(model_path=model_path)
    await _service.initialize()


def check_input(content: str) -> GuardrailResult:
    """Run Prompt Guard on inbound content (synchronous, blocking).

    Splits content into 512-token chunks with 50-token overlap.
    If any chunk triggers, entire input is blocked.

    Args:
        content: Input text to screen

    Returns:
        GuardrailResult with pass/fail decision
    """
    return _service._check_prompt_guard(content)


def check_output(content: str) -> GuardrailResult:
    """Run Llama Guard 3 on outbound content (synchronous, blocking).

    Full content classification against MLCommons taxonomy.
    Llama Guard 3 supports up to 131K tokens — suitable for long outputs.

    Args:
        content: Output text to classify

    Returns:
        GuardrailResult with pass/fail decision
    """
    return _service._check_llama_guard(content)


async def on_guardrail_fire(task_id: str, content: str, finding: str) -> None:
    """Handle guardrail fire — halt task, alert user.

    Updates task status in SQLite, adds to review queue, sends alert.

    Args:
        task_id: Task being halted
        content: Flagged content snippet
        finding: Guardrail reason
    """
    from src.db.store import AegisStore

    store = AegisStore()

    # 1. Update task status to HALTED
    await store.update_task(task_id, status="HALTED", halted_reason=finding)

    # 2. Add to review queue
    await store.add_review_item(
        type="guardrail_fire",
        task_id=task_id,
        details={"content_snippet": content[:500], "finding": finding}
    )

    # 3. Log alert
    logger.warning(f"GUARDRAIL FIRE on task {task_id}: {finding}")

    # 4. Email alert sent asynchronously (handled by email service)
    # This will be triggered by the review queue poller


def on_guardrail_fire_sync(task_id: str, content: str, finding: str) -> None:
    """Synchronous wrapper for guardrail fire handling.

    Use this when calling from synchronous contexts.
    """
    import asyncio
    try:
        loop = asyncio.get_running_loop()
        # If we're already in an event loop, create a task
        loop.create_task(on_guardrail_fire(task_id, content, finding))
    except RuntimeError:
        # No event loop running, use asyncio.run
        asyncio.run(on_guardrail_fire(task_id, content, finding))
