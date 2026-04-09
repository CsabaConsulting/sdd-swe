# Aegis — Technical Specification

**Version:** 1.0  
**Date:** 2026-04-09  
**Status:** Approved for implementation

---

## Architecture Overview

Aegis is a single-process Python application with modular architecture:

```
┌─────────────────────────────────────────────────────────────┐
│                      Orchestrator Engine                     │
│  (Finite State Machine: DISCOVERY→RESEARCH→DELIVERY→VALID→SUBMIT) │
└─────────────────────────────────────────────────────────────┘
         │                    │                    │
         ▼                    ▼                    ▼
┌─────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│  Skill Loader   │ │  Guardrail Fn    │ │  Wallet Client   │
│  (dynamic load) │ │  (direct import) │ │  (direct import) │
└─────────────────┘ └──────────────────┘ └──────────────────┘
         │                    │                    │
         ▼                    ▼                    ▼
┌─────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│  SKILL.md files │ │ Prompt Guard     │ │  Credential Env  │
│  (instructions) │ │ + Llama Guard 3  │ │  (never to LLM)  │
└─────────────────┘ └──────────────────┘ └──────────────────┘
         │
         ▼
┌─────────────────┐
│  LXC Sandbox    │
│  (code exec)    │
└─────────────────┘
```

**Key architectural principles:**
- **Single process:** Orchestrator + all modules run in one Python process
- **Direct imports:** Wallet and guardrails are function calls, not HTTP services
- **Progressive disclosure:** Only 1-2 skills active at a time based on phase
- **State persistence:** SQLite for all durable state, disk is source of truth
- **Provider-agnostic LLM:** OpenRouter first, adapters for local LLMs later

---

## Tech Stack

| Component | Technology | Rationale |
|-----------|------------|-----------|
| **Terminal UI** | `textual` (0.80+) | Structured TUI framework with regions, scrolling, color support |
| **Package Manager** | `uv` | Modern Python package management, fast dependency resolution |
| **State Persistence** | SQLite (built-in) | Single-file database, ACID guarantees, no external dependencies |
| **LLM Provider** | OpenRouter API | Multi-model access, fallback to local LLMs via adapters |
| **Retry Logic** | `tenacity` | Exponential backoff with jitter, customizable retry policies |
| **Email** | IMAP-only (polling every 60s) | No SendGrid dependency, agent polls Gmail for commands |
| **Code Sandbox** | LXC containers | Lightweight vs Docker, Linux-first, fast startup |
| **Guardrails** | Direct function imports | Llama Prompt Guard + Llama Guard 3 in isolated Python modules |
| **Observability** | OpenTelemetry + Phoenix | Self-hosted tracing, session replay, deep-linkable traces |

**Dependencies (pyproject.toml):**
```toml
[project]
name = "aegis"
version = "0.1.0"
requires-python = ">=3.12"

dependencies = [
    "textual>=0.80.0",    # TUI framework
    "openai",              # LLM abstraction (OpenRouter compatible)
    "tenacity",            # Retry with backoff
    "pydantic",            # Data validation
    "opentelemetry-api",   # Tracing
    "opentelemetry-sdk",
    "opentelemetry-exporter-otlp",
    "aiosqlite",           # Async SQLite
    "imaplib2",            # IMAP polling
    "python-dotenv",       # .env loading
]
```

---

## File Structure

```
sdd-swe/
├── docs/
│   ├── scope.md              # Project scope (read first)
│   ├── prd.md                # Product requirements (read second)
│   ├── learner-profile.md    # User context
│   └── spec.md               # This file (architecture)
├── src/
│   ├── cli/
│   │   ├── ui.py             # Main TUI (4 regions: main, side, status, prompt)
│   │   ├── commands.py       # Slash command handlers (/status, /skills, /tasks, etc.)
│   │   └── history.py        # Command output history, scroll-back persistence
│   ├── orchestrator/
│   │   ├── engine.py         # Finite state machine (phase transitions)
│   │   └── context.py        # Task context, correlation IDs, LLM state
│   ├── skills/
│   │   ├── catalog.py        # Scan built-in + cached skills
│   │   ├── loader.py         # Load SKILL.md based on phase
│   │   ├── vetting.py        # 3-gate verification (checksum, heuristic, sandbox)
│   │   ├── bidding_strategy.py # evaluate_task(), calculate_bid()
│   │   ├── research.py        # Web search, content analysis
│   │   ├── code_delivery.py   # Generate deliverables, write code
│   │   ├── validation.py      # LLM-as-judge checks
│   │   └── wallet_management.py # Submit results, check balance
│   ├── guardrails/
│   │   ├── service.py         # Prompt Guard + Llama Guard 3 (direct calls)
│   │   └── models/            # Model loading, caching
│   ├── wallet/
│   │   ├── client.py          # Direct function calls (place_bid, submit, balance)
│   │   └── vault.py           # Credential access (env vars, never exposed to LLM)
│   ├── execution/
│   │   └── sandbox.py         # LXC container lifecycle (create, execute, destroy)
│   ├── alerts/
│   │   └── email.py           # IMAP polling, command parsing, idempotency
│   ├── config/
│   │   └── loader.py          # .env parsing, API key validation
│   ├── telemetry/
│   │   └── tracer.py          # OpenTelemetry setup, Phoenix exporter
│   └── db/
│       └── store.py           # SQLite interface (tasks, skills, review queue)
├── skills/                     # Built-in SKILL.md files
│   ├── bidding-strategy/SKILL.md
│   ├── research/SKILL.md
│   ├── code-delivery/SKILL.md
│   ├── validation/SKILL.md
│   ├── wallet-management/SKILL.md
│   └── skill-vetting/SKILL.md
├── .agents/skills/cache/      # Downloaded skill cache (created at runtime)
├── tests/
│   ├── test_bidding.py
│   ├── test_validation.py
│   ├── test_guardrails.py
│   └── test_orchestrator.py
├── pyproject.toml
├── .env.example
└── README.md
```

---

## Component Details

### 1. Orchestrator Engine (`src/orchestrator/engine.py`)

**Implements:** `prd.md > Epic: System Observability` (user stories 1-4)

**Responsibilities:**
- Finite state machine with 5 phases: `PHASE_DISCOVERY`, `PHASE_RESEARCH`, `PHASE_DELIVERY`, `PHASE_VALIDATION`, `PHASE_SUBMISSION`
- Phase transitions based on task state
- Skill loading/unloading during transitions
- Task lifecycle management

**Phase transitions:**
```python
PHASE_DISCOVERY → PHASE_RESEARCH    # When bid won
PHASE_RESEARCH → PHASE_DELIVERY     # When research complete
PHASE_DELIVERY → PHASE_VALIDATION   # When deliverable ready
PHASE_VALIDATION → PHASE_DELIVERY   # When validation fails (max 3 iterations)
PHASE_VALIDATION → PHASE_SUBMISSION # When validation passes
PHASE_SUBMISSION → PHASE_DISCOVERY  # When submission complete
```

**Key functions:**
```python
def transition_phase(task_id: str, new_phase: Phase) -> None:
    """Transition task to new phase, unload old skill, load new skill"""
    ...

def run_discovery_cycle() -> None:
    """Scan /tasks, evaluate tasks, place bids"""
    ...

def handle_task_completion(task_id: str) -> None:
    """Archive completed task, notify user"""
    ...
```

---

### 2. Skill Management System

**Implements:** `prd.md > Epic: Skill Discovery & Management` (user stories 5-7)

#### 2a. Skill Loader (`src/skills/loader.py`)

**Responsibilities:**
- Load SKILL.md files based on phase
- Parse YAML frontmatter (name, description, compatibility)
- Unload skills during phase transitions

**SKILL.md format:**
```yaml
---
name: bidding-strategy
description: Evaluates tasks, calculates bid amounts
compatibility: Python 3.12+
---

# Bidding Strategy

## When to use
- During PHASE_DISCOVERY
- When scanning /tasks results

## How to use
1. Fetch task list
2. Evaluate skill fit
3. Calculate bid amount

## Safety notes
- Never bid outside specialization without approval
```

**Key functions:**
```python
def load_skill(skill_name: str) -> SkillSpec:
    """Load SKILL.md, parse frontmatter, return spec"""
    ...

def unload_skill(skill_name: str) -> None:
    """Remove skill from active context"""
    ...

def get_active_skills() -> list[str]:
    """Return list of currently loaded skills"""
    ...
```

#### 2b. Skill Catalog (`src/skills/catalog.py`)

**Responsibilities:**
- Scan built-in skills in `skills/` directory
- Scan cached skills in `.agents/skills/cache/`
- Search online catalogs (heilcheng, CommandCodeAI, MoizIbnYousaf, Copilot)
- Rank results by relevance, source reputation, last updated

**Catalog search flow:**
```python
def search_catalogs(keywords: str) -> list[SkillMatch]:
    """Search configured catalogs, return ranked results"""
    # 1. Query each catalog's search endpoint
    # 2. Rank by: relevance, reputation, recency
    # 3. Return top matches
    ...

def download_skill(skill_url: str) -> SkillSpec:
    """Download SKILL.md, verify checksum, return spec"""
    # 1. Download SKILL.md + checksum from catalog
    # 2. Verify checksum matches
    # 3. Return spec for vetting
    ...
```

#### 2c. Skill Vetting (`src/skills/vetting.py`)

**Responsibilities:**
- 3-gate verification for downloaded skills
- Gate 1: Checksum verification
- Gate 2: Heuristic scan for malicious patterns
- Gate 3: Sandboxed execution test

**Vetting flow:**
```python
def vet_skill(skill: SkillSpec) -> VettingResult:
    """Run 3-gate verification, return result"""
    # Gate 1: Checksum
    if not verify_checksum(skill):
        return VettingResult(rejected=True, reason="Checksum mismatch")
    
    # Gate 2: Heuristic scan
    scan_result = heuristic_scan(skill.content)
    if scan_result.suspicious:
        return VettingResult(rejected=True, reason=f"Suspicious: {scan_result.findings}")
    
    # Gate 3: Sandbox test
    sandbox_result = run_sandbox_test(skill)
    if not sandbox_result.passed:
        return VettingResult(rejected=True, reason="Sandbox execution failed")
    
    return VettingResult(approved=True)
```

---

### 3. Guardrail Service (`src/guardrails/service.py`)

**Implements:** `prd.md > Epic: Security & Safety` (user stories 8-10)

**Responsibilities:**
- Filter all LLM inputs through Prompt Guard (<10ms screening)
- Filter all LLM outputs through Llama Guard 3 (deep taxonomy)
- Immediate response on guardrail fire
- Task halt + alert generation

**Guardrail check:**
```python
def check_input(content: str) -> GuardrailResult:
    """Run Prompt Guard on inbound content"""
    # Synchronous call, blocks before LLM processing
    ...

def check_output(content: str) -> GuardrailResult:
    """Run Llama Guard 3 on outbound content"""
    # Synchronous call, blocks before execution
    ...

def on_guardrail_fire(task_id: str, content: str, finding: str) -> None:
    """Halt task, alert user, move to review queue"""
    # 1. Update task status to HALTED
    # 2. Add to review queue in SQLite
    # 3. Send email alert
    # 4. Log to terminal
    ...
```

**Guardrail behavior:**
- **Synchronous:** Orchestrator blocks until guardrail returns
- **No batching:** Each content check is individual
- **Immediate halt:** On fire, task stops instantly
- **User override:** `/force-approve <task-id>` bypasses guardrail (requires confirmation)

---

### 4. Wallet Client (`src/wallet/client.py`)

**Implements:** `prd.md > Epic: Bidding & Task Execution` (user stories 11-15)

**Responsibilities:**
- Direct function calls for UpMoltWork API
- Credential isolation (API key in env vars, never exposed to LLM)
- Retry logic with exponential backoff + jitter

**Key functions:**
```python
def place_bid(task_id: str, price_points: int, estimated_minutes: int, proposed_approach: str) -> BidResult:
    """POST /tasks/{taskId}/bids"""
    # Retry: tenacity, 5 attempts, exponential backoff + jitter
    ...

def submit_result(task_id: str, result_content: str, result_url: Optional[str] = None) -> SubmissionResult:
    """POST /tasks/{taskId}/submit"""
    ...

def get_balance() -> BalanceResult:
    """GET /points/balance"""
    ...

def estimate_time(task_description: str) -> int:
    """
    Heuristic-based duration estimate
    Uses LLM-as-estimator: call 3 times, take average
    """
    estimates = []
    for _ in range(3):
        response = llm.estimate_time(task_description)
        estimates.append(response.minutes)
    return int(sum(estimates) / len(estimates))
```

---

### 5. Code Execution Sandbox (`src/execution/sandbox.py`)

**Implements:** `prd.md > Epic: Security & Safety` (user story 10)

**Responsibilities:**
- Create ephemeral LXC container per code execution
- Disable network, restrict filesystem
- Execute tests, collect output, destroy container

**Sandbox lifecycle:**
```python
def execute_in_sandbox(code: str, test_command: str) -> ExecutionResult:
    """Run code in isolated LXC container"""
    # 1. Create LXC container
    container = lxc.create_container(f"sandbox-{uuid4().hex[:8]}")
    
    # 2. Configure security (network disabled, read-only fs)
    container.set_config("lxc.network.type", "none")
    container.set_config("lxc.rootfs.options", "ro")
    
    # 3. Write code to container
    container.write_file("/app/code.py", code)
    
    # 4. Execute test command
    result = container.execute(test_command, timeout=300)
    
    # 5. Collect output
    output = result.stdout
    exit_code = result.returncode
    
    # 6. Destroy container
    container.destroy()
    
    return ExecutionResult(output=output, exit_code=exit_code)
```

---

### 6. Validation Loop (`src/skills/validation.py`)

**Implements:** `prd.md > Epic: Bidding & Task Execution` (user story 14)

**Responsibilities:**
- LLM-as-judge checks for acceptance criteria compliance
- Architectural quality confidence check (configurable threshold, default 0.8)
- Iteration up to MAX_VALIDATION_ITERATIONS (default 3)

**Validation flow:**
```python
def validate_deliverable(task: TaskSpec, deliverable: str) -> ValidationResult:
    """Run validation checks, return result"""
    # Check 1: Acceptance criteria compliance
    criteria_result = llm_check_criteria(task.acceptance_criteria, deliverable)
    
    # Check 2: Architectural quality (confidence check)
    quality_confidence = llm_check_architecture(deliverable)
    
    if criteria_result.passed and quality_confidence >= VALIDATION_THRESHOLD:
        return ValidationResult(passed=True)
    
    # If only quality fails and iterations exhausted, submit anyway
    if quality_confidence < VALIDATION_THRESHOLD and iteration_count >= MAX_VALIDATION_ITERATIONS:
        return ValidationResult(passed=True, note="Quality compromised after max iterations")
    
    # Provide feedback for iteration
    return ValidationResult(
        passed=False, 
        feedback=f"Criteria issues: {criteria_result.issues}. Quality confidence: {quality_confidence}"
    )
```

---

## Data Flow Diagrams

### Diagram 1: Task Discovery → Submission Lifecycle

```
┌──────────────────────────────────────────────────────────────┐
│ PHASE_DISCOVERY                                              │
│  1. Orchestrator → GET /tasks (filter: status=open)          │
│  2. BiddingStrategy.evaluate_task(task) → skill_fit, etc     │
│  3. Wallet.estimate_time(task_desc) → avg of 3 LLM calls     │
│  4. Wallet.place_bid(task_id, points, minutes, approach)     │
│  5. SQLite: INSERT task (status=BIDDING)                     │
└──────────────────────────────────────────────────────────────┘
                            │
                            ▼ (bid accepted)
┌──────────────────────────────────────────────────────────────┐
│ PHASE_RESEARCH                                               │
│  6. Orchestrator transitions: unload bidding, load research  │
│  7. ResearchSkill.execute(task) → findings                   │
│  8. SQLite: UPDATE task (status=RESEARCH_COMPLETE)           │
└──────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│ PHASE_DELIVERY                                               │
│  9. Orchestrator transitions: unload research, load delivery │
│  10. CodeDeliverySkill.generate(task, research_findings)     │
│  11. If tests needed: SandboxExecutor.execute(code, tests)   │
│  12. SQLite: UPDATE task (status=DELIVERED)                  │
└──────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│ PHASE_VALIDATION                                             │
│  13. Orchestrator transitions: unload delivery, load validation│
│  14. ValidationSkill.check(deliverable, acceptance_criteria) │
│  15a. If fails: loop back to PHASE_DELIVERY (max 3x)         │
│  15b. If passes: continue to SUBMISSION                      │
└──────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│ PHASE_SUBMISSION                                             │
│  16. Wallet.submit_result(task_id, result_url/content)       │
│  17. SQLite: UPDATE task (status=SUBMITTED, points_earned)   │
│  18. Orchestrator transitions: back to DISCOVERY             │
└──────────────────────────────────────────────────────────────┘
```

### Diagram 2: Skill Discovery & Vetting Flow

```
┌──────────────────────────────────────────────────────────────┐
│ SKILL DISCOVERY                                              │
│  1. Orchestrator: "No built-in skill matches task keywords"  │
│  2. Catalog.search_catalogs(keywords) → list[SkillMatch]    │
│  3. Catalog.download_skill(skill_url) → SkillSpec            │
│  4. Verify checksum against catalog hash                     │
│  5a. If mismatch: reject, log alert                          │
│  5b. If match: continue                                      │
└──────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│ SKILL VETTING                                                │
│  6. SkillVetting.heuristic_scan(content)                     │
│     - Check for: credential patterns, command injection      │
│     - Check for: suspicious file operations                  │
│  7a. If suspicious: reject, log alert                        │
│  7b. If clean: continue                                      │
│                                                               │
│  8. SkillVetting.sandbox_test(skill)                         │
│     - Execute in LXC with network disabled                   │
│     - Monitor for: filesystem writes, unexpected behavior    │
│  9a. If sandbox fails: reject, log alert                     │
│  9b. If sandbox passes: continue                             │
└──────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│ SKILL APPROVAL                                               │
│  10. Check if first-time skill                               │
│  11a. If first-time: require human approval                  │
│      - Add to review queue in SQLite                         │
│      - Alert via terminal + email                            │
│      - Agent continues with other tasks                      │
│      - User: /approve <skill-name> or /reject <skill-name>   │
│  11b. If previously approved: skip approval                  │
│                                                               │
│  12. Cache skill in .agents/skills/cache/<name>/             │
│  13. Load skill into Orchestrator context                    │
│  14. Execute task with new skill                             │
└──────────────────────────────────────────────────────────────┘
```

### Diagram 3: Guardrail Check Flow

```
┌──────────────────────────────────────────────────────────────┐
│ INBOUND CONTENT CHECK                                        │
│  1. User input / task content arrives                        │
│  2. GuardrailService.check_input(content)                    │
│     - Run Prompt Guard (<10ms screening)                    │
│     - If Prompt Guard passes: continue                       │
│     - If Prompt Guard fires: halt immediately                │
└──────────────────────────────────────────────────────────────┘
                            │
                            ▼ (input passed)
┌──────────────────────────────────────────────────────────────┐
│ LLM PROCESSING                                               │
│  3. Orchestrator processes content                           │
│  4. LLM generates response                                   │
└──────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│ OUTBOUND CONTENT CHECK                                       │
│  5. GuardrailService.check_output(llm_response)              │
│     - Run Llama Guard 3 (deep taxonomy classification)       │
│     - If Guard passes: continue to execution                 │
│     - If Guard fires: halt, alert user                       │
└──────────────────────────────────────────────────────────────┘
                            │
                            ▼ (output passed)
┌──────────────────────────────────────────────────────────────┐
│ EXECUTION                                                    │
│  6. Execute LLM response (code run, API call, etc)           │
│  7. If guardrail fired at any point:                         │
│     - Task status = HALTED                                   │
│     - Add to review queue                                    │
│     - Send email alert                                       │
│     - Terminal alert in side column                          │
│     - User override via /force-approve <task-id>             │
└──────────────────────────────────────────────────────────────┘
```

---

## API Contracts

### UpMoltWork API Calls

**All API calls use `tenacity` for retries:**
- Max attempts: 5
- Backoff: 2^0, 2^1, 2^2, 2^3, 2^4 (1s, 2s, 4s, 8s, 16s) + random jitter (0-1s)
- After 5 failures: halt task, alert user

| Call | Method | Params | Returns | Notes |
|------|--------|--------|---------|-------|
| `register_agent` | `POST /agents/register` | `name`, `owner_twitter` | API key | One-time setup |
| `list_tasks` | `GET /tasks` | `status=open`, `category` (optional) | List[Task] | Public endpoint |
| `get_task` | `GET /tasks/{id}` | - | Task details | For acceptance criteria |
| `place_bid` | `POST /tasks/{taskId}/bids` | `price_points`, `estimated_minutes`, `proposed_approach` | Bid result | **`estimated_minutes` required** |
| `submit_result` | `POST /tasks/{taskId}/submit` | `result_url` OR `result_content` | Submission result | Prefer URL (Gist/repo) |
| `get_balance` | `GET /points/balance` | - | `balance_points`, `balance_usdc` | Check earnings |

### Task Filtering Logic

```python
def should_evaluate_task(task: Task) -> bool:
    """Determine if agent should bid on task"""
    # Filter 1: Only open tasks
    if task.status != "open":
        return False
    
    # Filter 2: Specialization match (if configured)
    if CONFIG.specializations and task.category not in CONFIG.specializations:
        return False
    
    # Filter 3: Prefer harder tasks (higher points)
    # No minimum threshold, but ranking considers points-to-effort ratio
    return True
```

### Time Estimation Heuristic

```python
async def estimate_time_minutes(task_description: str) -> int:
    """Use LLM to estimate task duration, call 3 times, take average"""
    estimates = []
    for _ in range(3):
        prompt = f"Estimate minutes for: {task_description}. Consider complexity, code size. Return integer only."
        response = await llm.complete(prompt)
        estimates.append(int(response.text))
    
    avg_estimate = sum(estimates) / len(estimates)
    return int(avg_estimate)
```

---

## State Management (SQLite Schema)

**Database file:** `aegis.db` (in project root)

### Table: `tasks`

```sql
CREATE TABLE tasks (
    id TEXT PRIMARY KEY,              -- UpMoltWork task ID
    title TEXT NOT NULL,
    description TEXT,
    acceptance_criteria TEXT,         -- JSON array of criteria
    category TEXT,
    points INTEGER,
    deadline TIMESTAMP,
    status TEXT NOT NULL,             -- DISCOVERED, BIDDING, RESEARCH, DELIVERY, VALIDATION, SUBMITTED, HALTED, ABANDONED
    phase TEXT,                       -- Current phase (only for active tasks)
    price_points_bid INTEGER,         -- Our bid amount
    estimated_minutes INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP,
    deliverable_content TEXT,         -- Full deliverable (or result_url)
    validation_iterations INTEGER DEFAULT 0,
    validation_feedback TEXT,         -- Last validation feedback
    halted_reason TEXT,               -- If halted: why
    metadata TEXT                     -- JSON: extra fields
);

CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_tasks_phase ON tasks(phase);
```

### Table: `skills`

```sql
CREATE TABLE skills (
    name TEXT PRIMARY KEY,
    source TEXT,                      -- "built-in" or catalog URL
    description TEXT,
    phase TEXT,                       -- Which phase uses this skill
    verification_status TEXT,         -- "not_verified", "pending_approval", "approved", "rejected"
    checksum TEXT,                    -- Catalog checksum (if downloaded)
    vetting_result TEXT,              -- JSON: heuristic scan result
    sandbox_log TEXT,                 -- JSON: sandbox execution log
    last_loaded_at TIMESTAMP,
    tasks_completed INTEGER DEFAULT 0, -- How many tasks used this skill
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for scanning cached skills
CREATE INDEX idx_skills_status ON skills(verification_status);
```

### Table: `review_queue`

```sql
CREATE TABLE review_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,               -- "guardrail_fire", "skill_approval"
    task_id TEXT,                     -- Task ID (if guardrail fire)
    skill_name TEXT,                  -- Skill name (if skill approval)
    details TEXT NOT NULL,            -- JSON: full details
    status TEXT NOT NULL,             -- "pending", "approved", "rejected"
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP
);

CREATE INDEX idx_review_status ON review_queue(status);
```

### Table: `command_log`

```sql
CREATE TABLE command_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    command TEXT NOT NULL,            -- Slash command or email command
    source TEXT NOT NULL,             -- "terminal" or "email"
    email_message_id TEXT,            -- IMAP message ID (if from email)
    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    result TEXT                       -- Command output (truncated)
);

-- Prevent replay attacks: track processed email IDs
CREATE UNIQUE INDEX idx_email_commands ON command_log(email_message_id);
```

---

## Error Handling & Retry Strategy

### API Failures

**All UpMoltWork API calls:**
```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=1, max=16),
    reraise=True
)
async def place_bid(task_id: str, ...) -> BidResult:
    """Place bid with retry logic"""
    try:
        return await wallet_client.place_bid(task_id, ...)
    except httpx.HTTPError as e:
        if e.response.status_code == 401:
            # API key invalid - halt immediately
            raise FatalError("API authentication failed")
        elif e.response.status_code == 402:
            # Insufficient balance - alert user
            raise FatalError("Insufficient balance")
        # Other errors: retry
        raise
```

### Guardrail Fire

**Immediate action:**
```python
async def handle_guardrail_fire(task_id: str, content: str, finding: str) -> None:
    """Halt task, add to review queue, alert user"""
    # 1. Update task
    await db.store.update_task(task_id, status="HALTED", halted_reason=finding)
    
    # 2. Add to review queue
    await db.store.add_review_item(
        type="guardrail_fire",
        task_id=task_id,
        details={"content_snippet": content[:500], "finding": finding}
    )
    
    # 3. Alert via terminal (side column)
    ui.show_alert(f"⚠️ Guardrail fired: {finding}")
    
    # 4. Send email alert
    await alerts.email.send_alert(
        subject=f"Aegis Alert: Guardrail Fired on Task {task_id}",
        body=f"Task halted. Flagged content: {content[:500]}\n\nAction: /review or /force-approve {task_id}"
    )
```

### Email Command Processing

**IMAP polling (every 60 seconds):**
```python
async def poll_email_commands() -> None:
    """Poll IMAP inbox for command replies, process idempotently"""
    async with imaplib.IMAP4_SSL(CONFIG.imap_host) as client:
        await client.login(CONFIG.imap_user, CONFIG.imap_pass)
        await client.select("INBOX")
        
        # Search for unread messages
        status, messages = await client.search(None, "UNSEEN")
        
        for msg_id in messages[0].split():
            # Fetch message
            msg = await client.fetch(msg_id, "(RFC822)")
            
            # Parse message ID (for idempotency)
            message_id = parse_message_id(msg)
            
            # Check if already processed (prevent replay)
            if await db.store.command_exists(message_id):
                continue
            
            # Parse command from subject line
            subject = parse_subject(msg)
            command = parse_command_from_subject(subject)
            
            # Execute command
            result = await commands.execute(command, source="email")
            
            # Mark as processed
            await db.store.log_command(command, source="email", email_message_id=message_id, result=result)
            
            # Mark as read
            await client.store(msg_id, "+FLAGS", "\\Seen")
```

---

## Observability (OpenTelemetry)

**All LLM calls, tool calls, phase transitions, skill activations are traced.**

### Trace Correlation

**Each task gets a `task_context_id`:**
```python
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

# Configure OTel exporter to Phoenix
otel_exporter = OTLPSpanExporter(endpoint="http://localhost:4317")
trace_provider = trace.TracerProvider()
trace_provider.add_span_processor(trace.BatchSpanProcessor(otel_exporter))

# Create task-correlated span
def create_task_span(task_id: str, operation: str) -> trace.Span:
    """Create span with task_context_id for correlation"""
    tracer = trace_provider.get_tracer("aegis")
    span = tracer.start_span(operation, attributes={
        "task_id": task_id,
        "task_context_id": f"task_{task_id}",
    })
    return span
```

### Key Traces

| Operation | Span Name | Attributes |
|-----------|-----------|------------|
| Phase transition | `orchestrator.phase_transition` | `task_id`, `from_phase`, `to_phase`, `duration_ms` |
| Skill activation | `skill.loaded` | `skill_name`, `source`, `phase`, `load_time_ms` |
| LLM call | `llm.completion` | `model`, `prompt_tokens`, `completion_tokens`, `latency_ms` |
| API call | `upmoltwork.api_call` | `method`, `path`, `status_code`, `latency_ms` |
| Guardrail check | `guardrail.check` | `direction` (in/out), `result` (pass/fire), `latency_ms` |
| Sandbox execution | `sandbox.execute` | `task_id`, `exit_code`, `duration_ms`, `network_blocked` (bool) |

**Phoenix UI deep link:** `http://localhost:6006/trace/{trace_id}`

---

## Configuration (.env)

```env
# Required
UPMOLTWORK_API_KEY=axe_...
OPENROUTER_API_KEY=sk-...
IMAP_HOST=imap.gmail.com
IMAP_USER=aegis@example.com
IMAP_PASS=app_password

# Optional (with defaults)
VALIDATION_CONFIDENCE_THRESHOLD=0.8
MAX_VALIDATION_ITERATIONS=3
GUARDRAIL_MODEL_PATH=/path/to/models
SPECIALIZATIONS=development,content
EMAIL_POLL_INTERVAL_SECONDS=60
```

**Validation on startup:**
```python
async def validate_config() -> None:
    """Check API keys, validate connectivity"""
    # 1. Validate UPMOLTWORK_API_KEY
    try:
        await wallet_client.get_balance()
    except httpx.HTTPError:
        raise ConfigurationError("UPMOLTWORK_API_KEY invalid or API unreachable")
    
    # 2. Validate OPENROUTER_API_KEY
    try:
        await llm.test_connection()
    except Exception:
        raise ConfigurationError("OPENROUTER_API_KEY invalid")
    
    # 3. Test IMAP
    try:
        await imaplib.test_connection()
    except Exception:
        raise ConfigurationError("IMAP credentials invalid")
```

---

## Testing Strategy

### Unit Tests

**Coverage areas:**
- `tests/test_bidding.py`: Bidding strategy evaluation, time estimation
- `tests/test_validation.py`: Validation loop, iteration limits
- `tests/test_guardrails.py`: Guardrail check logic, fire handling
- `tests/test_orchestrator.py`: Phase transitions, skill loading/unloading
- `tests/test_skill_vetting.py`: Checksum verification, heuristic scan
- `tests/test_sandbox.py`: LXC container lifecycle
- `tests/test_email.py`: IMAP polling, command parsing, idempotency

### Integration Tests

**Test scenarios:**
- Full task lifecycle: DISCOVERY → SUBMISSION
- Skill discovery + vetting + approval flow
- Guardrail fire + task halt + override
- Validation loop: 3 iterations, then submit
- Email command: reply with `/approve`, verify execution

### End-to-End Test

**Mock UpMoltWork server:**
```python
# tests/e2e/test_full_cycle.py
async def test_full_task_lifecycle():
    """Simulate full task lifecycle with mock API"""
    # 1. Start agent
    agent = AegisAgent(test_config=True)
    await agent.start()
    
    # 2. Mock task appears
    mock_task = create_mock_task(status="open", points=150)
    agent.mock_api.add_task(mock_task)
    
    # 3. Wait for bid
    await asyncio.sleep(10)
    assert agent.db.get_task(mock_task.id).status == "BIDDING"
    
    # 4. Accept bid (mock)
    agent.mock_api.accept_bid(mock_task.id)
    
    # 5. Wait for submission
    await asyncio.sleep(60)
    assert agent.db.get_task(mock_task.id).status == "SUBMITTED"
```

---
