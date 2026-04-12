# Aegis Test Suite

Comprehensive test suite for the Aegis autonomous agent system.

## Quick Start

```bash
# Run all tests
uv run pytest -v

# Run with coverage
uv run pytest --cov=src --cov-report=term-missing

# Run specific test module
uv run pytest tests/test_guardrails.py -v
```

## Test Structure

| File | Covers |
|------|--------|
| `conftest.py` | Shared fixtures: mock config, temp databases, mock API/LLM clients |
| `utils.py` | Helper functions: `create_mock_task()`, `assert_task_status()`, JSON helpers |
| `test_infrastructure.py` | Infrastructure verification tests |
| `test_guardrails.py` | Guardrail service: chunking, Prompt Guard, Llama Guard, fire handlers |
| `test_sandbox.py` | Sandbox execution: Podman, subprocess fallback, timeouts, cleanup |
| `test_bidding.py` | Bidding strategy: task evaluation, bid calculation, confidence |
| `test_validation.py` | Validation loop: criteria checks, iteration tracking, confidence threshold |
| `test_orchestrator.py` | State machine: phase transitions, skill loading, halt scenarios |
| `test_store.py` | SQLite store: CRUD, review queue, command idempotency |
| `test_config.py` | Config loader: .env parsing, validation, error handling |
| `test_integration_lifecycle.py` | Full lifecycle: discovery → bidding → research → delivery → validation → submission |

## Fixtures (from conftest.py)

- `mock_config` — Test AegisConfig with fake credentials (no .env needed)
- `mock_config_low_threshold` — Config with lower validation threshold
- `temp_db` — Temporary SQLite database with initialized tables (async)
- `temp_db_path` — Just the temp database path
- `mock_api_client` — Mock UpMoltWork API with pre-loaded test tasks
- `mock_llm_client` — Mock LLM with predictable responses
- `patch_vault_credentials` — Patches wallet vault to return test keys
- `patch_httpx_client` — Prevents real HTTP calls

## Test Utilities (from utils.py)

```python
from tests.utils import create_mock_task, assert_task_status, json_contains

# Create realistic test task
task = create_mock_task(task_id="test-001", points=500, status="BIDDING")

# Assert task state
assert_task_status(task, "SUBMITTED")

# JSON containment check
assert json_contains(actual_response, {"status": "ok"})
```

## Writing New Tests

1. Create `tests/test_<module>.py`
2. Use existing fixtures from `conftest.py`
3. Mock external dependencies (LLM, API, models)
4. Use `temp_db` fixture for database tests
5. Follow naming: `test_<functionality>()` methods in `Test<Class>` classes

## Coverage

```bash
uv run pytest --cov=src --cov-report=html
# Open htmlcov/index.html in browser
```

Target: >70% coverage of core modules (guardrails, sandbox, bidding, validation, orchestrator, store, config).
