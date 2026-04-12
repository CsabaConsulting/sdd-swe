# Aegis — Build Checklist

**Build Mode:** Autonomous (no verification checkpoints)
**Verification:** Disabled
**Comprehension Checks:** N/A
**Git Cadence:** Commit after each item
**Check-in Cadence:** N/A (autonomous)
**Estimated Total Build Time:** 3-4 hours
**Total Items:** 12

---

## Build Plan

Ordered by dependency: SQLite store → config → wallet → UI → orchestrator → skills → guardrails → sandbox → validation → email → bidding → Devpost submission.

Each item references a specific `spec.md` subsection and maps to PRD epics.

---

## Checklist

- [x] **1. SQLite Schema + Store Interface**
  Spec ref: `spec.md > State Management (SQLite Schema)`
  What to build: Create `aegis.db` with 4 tables (tasks, skills, review_queue, command_log). Implement `src/db/store.py` with async SQLite interface: `add_task()`, `update_task()`, `get_task()`, `add_skill()`, `update_skill()`, `add_review_item()`, `log_command()`. Include indexes for status/phase queries.
  Acceptance: `aegis.db` exists with all 4 tables, correct schemas, and indexes. Can insert/query tasks and skills via store interface.
  Verify: Run `python -m src.db.store` (add test mode) and confirm tables created, inserts work, queries return expected results.

- [x] **2. Config Loader + .env Validation**
  Spec ref: `spec.md > Configuration (.env)`
  What to build: Implement `src/config/loader.py` to read `.env` using `python-dotenv`. Validate required vars (UPMOLTWORK_API_KEY, OPENROUTER_API_KEY, IMAP_HOST, IMAP_USER, IMAP_PASS). Parse optional vars with defaults (VALIDATION_CONFIDENCE_THRESHOLD=0.8, MAX_VALIDATION_ITERATIONS=3, etc.). Implement `validate_config()` function that tests API connectivity (UpMoltWork balance check, OpenRouter test call, IMAP login test).
  Acceptance: Application starts only when all required env vars are present and valid. Clear error messages for missing/invalid vars. Optional vars fall back to defaults.
  Verify: Run without `.env` (should fail with "Missing UPMOLTWORK_API_KEY"). Add `.env` with valid keys and confirm `validate_config()` passes all 3 checks.

- [x] **3. Wallet Client (UpMoltWork API)**
  Spec ref: `spec.md > Component Details > 4. Wallet Client`
  What to build: Implement `src/wallet/client.py` with direct async functions: `place_bid()`, `submit_result()`, `get_balance()`, `estimate_time()`. Add `tenacity` retry logic (5 attempts, exponential backoff + jitter) to all API calls. Implement `src/wallet/vault.py` for credential isolation (reads from env vars, never exposes to LLM). `estimate_time()` calls LLM 3 times and returns average.
  Acceptance: All UpMoltWork API endpoints callable via wallet client. Retries work on transient failures. `estimated_minutes` uses 3-call average. Credentials never logged or exposed.
  Verify: Call `get_balance()` and confirm it returns points + USDC. Call `estimate_time("Write a Python CLI")` and confirm it returns an integer average of 3 LLM calls.

- [x] **4. Terminal UI Skeleton (4 Regions)**
  Spec ref: `spec.md > File Structure > src/cli/`
  What to build: Implement `src/cli/ui.py` using `textual` framework. Create 4-region layout: Main view (scrollable task list), Side column (errors + info messages), Status line (summary counts), Command prompt (slash commands). Implement `src/cli/history.py` for command output persistence. Implement `src/cli/commands.py` stub handlers for `/status`, `/skills`, `/tasks`, `/review`, `/balance`.
  Acceptance: Terminal renders 4 distinct regions with borders. Main view shows placeholder tasks. Side column shows placeholder errors. Status line displays counts. Command prompt accepts input. Slash commands return stub responses.
  Verify: Run `python -m src.cli.ui` and confirm all 4 regions render. Type `/status` and confirm stub response appears. Scroll through main view.

- [x] **5. Orchestrator Engine (State Machine)**
  Spec ref: `spec.md > Component Details > 1. Orchestrator Engine`
  What to build: Implement `src/orchestrator/engine.py` with finite state machine: 5 phases (DISCOVERY, RESEARCH, DELIVERY, VALIDATION, SUBMISSION). Implement `transition_phase()` function that updates task phase in SQLite, unloads old skill, loads new skill. Implement `run_discovery_cycle()` that scans `/tasks`, evaluates tasks, places bids. Implement `handle_task_completion()`.
  Acceptance: Orchestrator can transition between all 5 phases. Phase transitions logged to SQLite. Skills load/unload based on phase. Discovery cycle scans tasks and places bids.
  Verify: Create a test task in SQLite with status=BIDDING. Call `transition_phase(task_id, PHASE_RESEARCH)` and confirm phase updates in DB, old skill unloads, new skill loads.

- [x] **6. Skill Loader + Catalog Scanner**
  Spec ref: `spec.md > Component Details > 2a. Skill Loader` and `2b. Skill Catalog`
  What to build: Implement `src/skills/loader.py` with `load_skill()` (parses SKILL.md YAML frontmatter), `unload_skill()`, `get_active_skills()`. Implement `src/skills/catalog.py` with `scan_builtin_skills()` (scans `skills/` directory), `scan_cached_skills()` (scans `.agents/skills/cache/`), `search_catalogs()` (queries online catalogs). Create 5 built-in SKILL.md files in `skills/` directory (bidding-strategy, research, code-delivery, validation, wallet-management) with proper YAML frontmatter.
  Acceptance: Can load/unload skills by name. Catalog scanner finds all 5 built-in skills. Cached skills detected if present. Catalog search returns ranked results.
  Verify: Call `load_skill("bidding-strategy")` and confirm it parses frontmatter correctly. Call `scan_builtin_skills()` and confirm it finds all 5 SKILL.md files.

- [x] **7. Guardrail Service (Direct Function Imports)**
  Spec ref: `spec.md > Component Details > 3. Guardrail Service`
  What to build: Implement `src/guardrails/service.py` with `check_input()` (Prompt Guard on inbound content), `check_output()` (Llama Guard 3 on outbound content), `on_guardrail_fire()` (halt task, add to review queue, alert user). Models loaded from `src/guardrails/models/` directory. All checks synchronous and blocking. Guardrail fires halt tasks immediately.
  Acceptance: All LLM inputs/outputs pass through guardrails. Guardrail fires halt tasks and add to review queue. Terminal alert appears in side column. Email alert sent on fire.
  Verify: Call `check_input("normal content")` and confirm it passes. Call `check_output("malicious payload")` and confirm it fires (or stub for now if models not loaded). Confirm `on_guardrail_fire()` adds task to review_queue table.

- [x] **8. LXC Sandbox Executor**
  Spec ref: `spec.md > Component Details > 5. Code Execution Sandbox`
  What to build: Implement `src/execution/sandbox.py` with `execute_in_sandbox()` function. Create ephemeral LXC container, configure security (network disabled, read-only filesystem), write code to container, execute test command with timeout, collect output, destroy container. Return `ExecutionResult` with stdout + exit code.
  Acceptance: Code executes in isolated LXC container. Network is disabled. Filesystem is read-only. Container destroyed after execution. Output captured.
  Verify: Call `execute_in_sandbox("print('hello')", "python code.py")` and confirm it returns exit_code=0 with correct output. Confirm container is destroyed after execution.

- [x] **9. Validation Loop (LLM-as-Judge)**
  Spec ref: `spec.md > Component Details > 6. Validation Loop`
  What to build: Implement `src/skills/validation.py` with `validate_deliverable()` function. Check 1: Acceptance criteria compliance via LLM. Check 2: Architectural quality confidence via LLM (configurable threshold, default 0.8). If validation fails, loop back to delivery (max 3 iterations). If only quality fails after 3 iterations, submit anyway with note.
  Acceptance: Validation checks both criteria compliance AND quality confidence. Iteration count tracked. After 3 iterations, submits even if only quality fails. Feedback provided for each iteration.
  Verify: Call `validate_deliverable(task, "good code")` and confirm it returns `passed=True`. Call with "bad code" and confirm it returns `passed=False` with feedback. Call 3 times and confirm it submits on 3rd iteration even if quality low.

- [x] **10. Email Alerts (IMAP Polling)**
  Spec ref: `spec.md > Error Handling & Retry Strategy > Email Command Processing`
  What to build: Implement `src/alerts/email.py` with `poll_email_commands()` function. Poll IMAP inbox every 60 seconds, parse subject line for commands (`/approve`, `/halt`, `/force-approve`), execute commands, track processed message IDs in `command_log` table to prevent replay. Send alerts via IMAP (no SendGrid dependency).
  Acceptance: Email commands parsed from subject lines. Commands executed idempotently (no replays). Processed message IDs tracked. Alerts sent via IMAP.
  Verify: Send email with subject "Aegis Alert: /approve test-skill". Wait 60s. Confirm command executed and logged in `command_log` table. Send same email again and confirm it's ignored (idempotency).

- [x] **11. Bidding Strategy + Time Estimation**
  Spec ref: `spec.md > API Contracts > Task Filtering Logic` and `Time Estimation Heuristic`
  What to build: Implement `src/skills/bidding_strategy.py` with `evaluate_task()` (skill fit, points-to-effort ratio), `calculate_bid()` (price_points, estimated_minutes, proposed_approach). `estimated_minutes` uses LLM 3-call average. Filter tasks by `status=open`, prefer harder tasks. Place bids via `wallet.client.place_bid()`.
  Acceptance: Tasks filtered correctly (open only, specialization match). Bid calculation considers complexity + reputation. Time estimation averages 3 LLM calls. Bids placed successfully via wallet.
  Verify: Call `evaluate_task(mock_task)` and confirm it returns skill_fit, points_to_effort, confidence. Call `calculate_bid(mock_task)` and confirm it returns price_points, estimated_minutes (integer from 3-call average), proposed_approach.

- [x] **12. Devpost Submission Preparation**
Spec ref: `spec.md > Error Handling & Retry Strategy > Email Command Processing`
  What to build: Replace stub in `src/alerts/email.py` with actual IMAP implementation. Connect to IMAP server using credentials from vault. Poll every 60 seconds. Parse subject lines for commands (`/approve`, `/halt`, `/force-approve`). Execute commands via `src/cli/commands.py`. Track processed message IDs for idempotency. Send alerts via IMAP.
  Acceptance: IMAP connection works. Commands parsed from subject lines. Commands executed idempotently (no replays — message ID tracking). Alerts sent via email.
  Verify: Configure `.env` with IMAP credentials. Run agent. Send email with subject "Aegis: /approve test-skill". Confirm command executed within 60s. Send same email again and confirm it's ignored (idempotency).
  Spec ref: `spec.md > Architecture Overview` (for project description) and `docs/prd.md` (for user stories)
  What to build: Prepare Devpost submission page: (1) Write compelling project description based on scope + PRD. (2) Take 5 screenshots: terminal UI with tasks, side column guardrail alert, skill approval request, `/skills` command output, Phoenix trace view. (3) Create GitHub repo if not exists, commit all code, push to GitHub. (4) Prepare submission narrative: core story, "wow moment" (3-gate skill verification), technical approach. (5) Optional: record 2-min demo video.
  Acceptance: Devpost submission page complete with description, 5+ screenshots, GitHub repo link, core story, and "wow moment" clearly articulated. Code pushed to GitHub.
  Verify: Open Devpost submission page in browser and confirm all sections filled. Click GitHub link and confirm code is accessible. Review screenshots and confirm they show key features.

## Iteration 1 — Stub Implementation

- [x] **1. Validation Loop — LLM-as-Judge Implementation**
  Spec ref: `spec.md > Component Details > 6. Validation Loop`
  What to build: Replace stub in `src/skills/validation.py` with actual LLM calls. Implement `llm_check_criteria()` that sends acceptance criteria + deliverable to LLM, parses compliance check. Implement `llm_check_architecture()` that sends deliverable code, gets quality confidence score (0.0-1.0). Use OpenRouter via `src/wallet/vault.py` for credentials. Parse LLM responses with pydantic models.
  Acceptance: Validation actually calls LLM twice (criteria + architecture). Returns real confidence scores. Feedback includes specific issues found. Iteration tracking works (max 3 retries).
  Verify: Call `validate_deliverable()` with mock task + deliverable. Confirm LLM is called, confidence score returned, feedback is meaningful (not hardcoded).

- [x] **2. Bidding Strategy — LLM Task Evaluation**
  Spec ref: `spec.md > API Contracts > Task Filtering Logic`
  What to build: Replace stub in `src/skills/bidding_strategy.py` `evaluate_task()` with actual LLM analysis. LLM analyzes task description for complexity, checks against specializations, calculates points-to-effort ratio. Returns `skill_fit` (bool), `points_to_effort` (float), `confidence` (0.0-1.0), `recommended_points` (int), `approach` (LLM-generated strategy).
  Acceptance: `evaluate_task()` calls LLM for complexity analysis. Returns realistic confidence based on task complexity. `approach` field contains LLM-generated strategy, not hardcoded text.
  Verify: Call `evaluate_task(mock_task)` with different task complexities. Confirm LLM is called, confidence varies by task, approach is task-specific.

- [x] **3. Guardrail Service — Model Loading (Prompt Guard + Llama Guard 3)**
  Spec ref: `spec.md > Component Details > 3. Guardrail Service`
  What to build: Replace stub in `src/guardrails/service.py` with actual model loading. Add `transformers`, `torch`, `sentencepiece` dependencies. Load Llama Prompt Guard 2 (86M) for `check_input()` with iterative chunking (512 tokens, 50 overlap). Load Llama Guard 3 (8B) for `check_output()`. Implement async model caching (load once, reuse). Handle model loading failures gracefully (degraded mode).
  Acceptance: Guardrail models load asynchronously on startup. `check_input()` screens with chunked Prompt Guard. `check_output()` classifies via Llama Guard 3. Guardrail fires halt tasks, add to review queue. Graceful fallback if models unavailable.
  Verify: Call `check_input()` with benign content (passes). Call with injection (fires). Call `check_output()` with safe/unsafe content and confirm classification. Check `initialize_guardrails()` loads models without errors.
  Status: IMPLEMENTED — two-stage pipeline, chunking, degraded mode fallback

- [x] **4. Code Execution Sandbox — Podman with Subprocess Fallback**
  Spec ref: `spec.md > Component Details > 5. Code Execution Sandbox`
  What to build: Replace stub in `src/execution/sandbox.py` with Podman container management via `podman-py`. Add `podman` dependency. Implement container creation with security: network disabled, read-only filesystem, resource limits (CPU, memory, file size), auto-destroy. If Podman unavailable, fall back to subprocess with `tempfile` isolation + `resource` limits + security warning. Add startup check in `src/config/loader.py`.
  Acceptance: Code executes in Podman container when available. Network disabled, filesystem read-only. Container destroyed after execution. Exit code and stdout captured. Timeout enforced. If Podman unavailable, subprocess fallback with warnings and weaker isolation.
  Verify: Call `execute_in_sandbox("print('hello')", "python code.py")` and confirm exit_code=0, output="hello", mode="podman" (or "subprocess" if podman not installed). Confirm cleanup. Test timeout with long-running code. Run `python -m src.config.loader` and confirm podman check passes or warns.
  Status: IMPLEMENTED — podman-py primary, subprocess fallback with resource limits

- [x] **5. Email Alerts — IMAP Polling**
  Spec ref: `spec.md > Error Handling & Retry Strategy > Email Command Processing`
  What to build: Replace stub in `src/alerts/email.py` with actual IMAP implementation. Connect to IMAP server using credentials from vault. Poll every 60 seconds. Parse subject lines for commands (`/approve`, `/halt`, `/force-approve`). Execute commands via `src/cli/commands.py`. Track processed message IDs for idempotency. Send alerts via IMAP.
  Acceptance: IMAP connection works. Commands parsed from subject lines. Commands executed idempotently (no replays — message ID tracking). Alerts sent via email.
  Verify: Configure `.env` with IMAP credentials. Run agent. Send email with subject "Aegis: /approve test-skill". Confirm command executed within 60s. Send same email again and confirm it's ignored (idempotency).

## Iteration 2 — Test Suite (Unit + Integration)

- [x] **1. Test Infrastructure + Fixture Setup**
  Spec ref: New — not in original spec
  What to build: Create `tests/` directory structure with `conftest.py` (shared fixtures: mock config, temp databases, mock API client), `pytest.ini` config, test utilities. Add `pytest`, `pytest-asyncio`, `pytest-mock` to dev dependencies in `pyproject.toml`. Create `tests/utils.py` for helper functions.
  Acceptance: `pytest -v` discovers and runs all tests. Fixtures are reusable across test modules. Temp databases cleaned up after each test. Mock config provides valid test credentials without real `.env` file.
  Verify: Run `pytest -v` from project root — all collection works, fixtures accessible. Confirm temp DB created/destroyed per test.

- [x] **2. Unit Tests — Guardrail Service**
  Spec ref: `spec.md > Component Details > 3. Guardrail Service`
  What to build: Test `src/guardrails/service.py`: `_chunk_content()` with 512-token chunks + 50 overlap, `_check_prompt_guard()` pass/fire scenarios, `_check_llama_guard()` pass/fire scenarios, degraded mode (models not loaded), `on_guardrail_fire()` (updates task, adds to review_queue). Mock `transformers`/`torch` to avoid model downloads.
  Acceptance: Chunking splits long content correctly. Guardrail checks return correct pass/fail with confidence scores. Degraded mode passes with warning. Fire handler updates SQLite correctly. All tests run without actual model loading (<1s each).
  Verify: `pytest tests/test_guardrails.py -v` — all 8-10 tests pass. Confirm no model downloads during tests. Check SQLite updates after fire test.

- [x] **3. Unit Tests — Sandbox Execution**
  Spec ref: `spec.md > Component Details > 5. Code Execution Sandbox`
  What to build: Test `src/execution/sandbox.py`: Podman execution (mock `podman-py`), subprocess fallback, timeout enforcement (kill after 300s), resource limits, cleanup (temp dir removal). Test `check_podman_available()` with/without podman. Mock subprocess for safe execution.
  Acceptance: Podman path returns `sandbox_mode="podman"`. Subprocess path returns `sandbox_mode="subprocess"`. Timeout kills process. Temp directory cleaned up after execution. Podman check returns correct bool.
  Verify: `pytest tests/test_sandbox.py -v` — all tests pass. Confirm no orphan containers/temp dirs after tests. Test timeout with mock long-running command.
  Status: IMPLEMENTED — tests written, mocking podman-py and subprocess

- [x] **4. Unit Tests — Bidding Strategy**
  Spec ref: `spec.md > API Contracts > Task Filtering Logic` and `Time Estimation Heuristic`
  What to build: Test `src/skills/bidding_strategy.py`: `evaluate_task()` with mock LLM analysis, `calculate_bid()` output format, skill_fit logic (specialization match/mismatch), confidence scoring, points_to_effort calculation. Mock OpenRouter calls with `pytest-mock`.
  Acceptance: `evaluate_task()` returns realistic skill_fit, confidence varies by task complexity. `calculate_bid()` returns correct format (price_points, estimated_minutes, approach). Specialization filtering works correctly.
  Verify: `pytest tests/test_bidding.py -v` — all tests pass. Mock LLM returns predictable responses. No real API calls made.
  Status: IMPLEMENTED — tests mock LLM, evaluate bid strategies

- [x] **5. Unit Tests — Validation Loop**
  Spec ref: `spec.md > Component Details > 6. Validation Loop`
  What to build: Test `src/skills/validation.py`: `validate_deliverable()` with criteria + architecture checks, iteration tracking (0→3), max iteration behavior (submit after 3 even if quality fails), confidence threshold enforcement (0.8 default). Mock LLM calls.
  Acceptance: Validation passes when both criteria met + quality >= threshold. Fails and provides feedback when criteria missing. After 3 iterations, submits anyway with note. Confidence threshold configurable.
  Verify: `pytest tests/test_validation.py -v` — all tests pass. Confirm iteration count tracked in SQLite. Test threshold edge cases (0.79 vs 0.80).
  Status: IMPLEMENTED — tests mock validation LLM, iteration tracking

- [x] **6. Unit Tests — Orchestrator State Machine**
  Spec ref: `spec.md > Component Details > 1. Orchestrator Engine`
  What to build: Test `src/orchestrator/engine.py`: Phase transitions (DISCOVERY→RESEARCH→DELIVERY→VALIDATION→SUBMISSION), skill loading/unloading during transitions, task status updates in SQLite, halt scenarios (guardrail fire). Verify phase transition log entries.
  Acceptance: Phase transitions update task phase in SQLite. Old skill unloaded, new skill loaded. Invalid transitions rejected. Halt scenarios update status to HALTED. Phase log entries created.
  Verify: `pytest tests/test_orchestrator.py -v` — all tests pass. Confirm SQLite reflects correct phase after transitions. Check skill load/unload tracking.
  Status: IMPLEMENTED — tests mock orchestrator phases

- [x] **7. Unit Tests — SQLite Store**
  Spec ref: `spec.md > State Management (SQLite Schema)`
  What to build: Test `src/db/store.py`: CRUD operations (add_task, update_task, get_task), skill operations, review_queue operations (add, get, resolve), command_log idempotency (email_message_id uniqueness), status queries (get_tasks_by_status). Use temp databases per test.
  Acceptance: All CRUD operations work correctly. Indexes exist for status/phase queries. Email message ID uniqueness enforced (IntegrityError on duplicate). Review queue operations return correct items. Temp databases cleaned up.
  Verify: `pytest tests/test_store.py -v` — all tests pass. Confirm indexes created in schema. Test idempotency by inserting duplicate email IDs (should raise).
  Status: IMPLEMENTED — tests use temp_db fixture, CRUD + idempotency

- [x] **8. Unit Tests — Config Loader**
  Spec ref: `spec.md > Configuration (.env)`
  What to build: Test `src/config/loader.py`: .env parsing with defaults, missing var errors (ConfigurationError raised), IMAP connection test (mocked), podman check (mocked), `validate_config()` flow. Test both valid and invalid configs.
  Acceptance: Missing required vars raise ConfigurationError with clear message. Optional vars fall back to defaults. Validation tests API connectivity (mocked). Podman check returns correct bool + warning.
  Verify: `pytest tests/test_config.py -v` — all tests pass. Confirm error messages are user-friendly. Test with partial .env (some vars missing).
  Status: IMPLEMENTED — tests mock config validation

- [x] **9. Integration Test — Full Task Lifecycle**
  Spec ref: `spec.md > Data Flow Diagrams > Diagram 1: Task Discovery → Submission Lifecycle`
  What to build: End-to-end test with mock UpMoltWork API: Create mock task in SQLite → Discovery (evaluate_task) → Bidding (mock accept) → Research → Delivery → Validation → Submission. Verify SQLite state changes at each phase. Use `pytest-asyncio`, mock HTTP responses with `respx` or `httpx.MockTransport`.
  Acceptance: Full lifecycle completes without errors. Task progresses through all 5 phases. SQLite reflects correct status at each step. Wallet API calls mocked successfully. Validation passes or loops correctly.
  Verify: `pytest tests/test_integration_lifecycle.py -v` — single integration test passes. Takes <30s. Confirms end-to-end flow works with mocked external dependencies.
  Status: IMPLEMENTED — integration test mocks full lifecycle

- [x] **10. Test Documentation + CI Readiness**
  Spec ref: New — not in original spec (but implied by `spec.md > Testing Strategy`)
  What to build: Create `tests/README.md` explaining how to run tests (`pytest -v`), test structure, fixture usage. Add test script to `pyproject.toml`: `[project.scripts] pytest = "pytest"` or `[tool.pytest.ini_options]`. Add `pytest-cov` for coverage report if easy. Verify all tests pass with `pytest -v`.
  Acceptance: `pytest -v` from project root runs all tests successfully. README explains test setup clearly. Coverage report shows >70% coverage of core modules (optional). No test failures.
  Verify: `cd /home/csaba/repos/SDD/sdd-swe && pytest -v --tb=short` — all tests pass. Coverage report generated if configured. New developer can run tests following README.
  Status: IMPLEMENTED — README.md created, pyproject.toml configured
