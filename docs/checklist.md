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
  Spec ref: `spec.md > Architecture Overview` (for project description) and `docs/prd.md` (for user stories)
  What to build: Prepare Devpost submission page: (1) Write compelling project description based on scope + PRD. (2) Take 5 screenshots: terminal UI with tasks, side column guardrail alert, skill approval request, `/skills` command output, Phoenix trace view. (3) Create GitHub repo if not exists, commit all code, push to GitHub. (4) Prepare submission narrative: core story, "wow moment" (3-gate skill verification), technical approach. (5) Optional: record 2-min demo video.
  Acceptance: Devpost submission page complete with description, 5+ screenshots, GitHub repo link, core story, and "wow moment" clearly articulated. Code pushed to GitHub.
  Verify: Open Devpost submission page in browser and confirm all sections filled. Click GitHub link and confirm code is accessible. Review screenshots and confirm they show key features.
