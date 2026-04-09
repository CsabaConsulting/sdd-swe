# Process Notes

## /scope

### Architectural Evolution

**Initial design:** Multi-agent P2P system with 5 separate processes (Orchestrator, Coder, Researcher, Validator, Wallet), each running as independent A2A agents communicating via HTTP.

**Pivot point:** User introduced Agent Skills specification (agentskills.io) as alternative to fixed agents. Dynamic skill loading/unloading via SKILL.md files in `.agents/skills/` directories.

**Final architecture (hybrid):**
- **One Orchestrator process** with dynamic skill loading based on finite state machine phases
- **5 built-in skills** (bidding-strategy, research, code-delivery, validation, wallet-management) + **1 security skill** (skill-vetting)
- **Dynamic skill discovery** — Orchestrator searches online catalogs, downloads + verifies + sandboxes new skills autonomously
- **Wallet HTTP service** — Not an LLM agent, just a credential-isolation service exposed via API
- **Guardrail services** — Separate ML model containers (Prompt Guard + Llama Guard)
- **Code execution sandbox** — Docker-in-Docker per task

### Key Design Decisions

1. **Progressive disclosure pattern** — Skills loaded/unloaded based on task phase. Only 1-2 skills active at a time. Prevents context bloat.
2. **Trust model for 3rd party skills** — 3-gate verification: (1) Checksum verification, (2) skill-vetting agent scan, (3) Sandboxed execution test. First-time skills require human approval.
3. **Wallet as service, not agent** — Credentials isolated in HTTP API, never exposed to LLM context. Orchestrator calls endpoints via `wallet_client.py`.
4. **Dynamic skill discovery = core differentiator** — Aegis autonomously searches 4 default catalogs (heilcheng, CommandCodeAI, MoizIbnYousaf, Copilot), evaluates relevance, downloads + verifies + activates new skills. Custom skill generation = post-hackathon feature.
5. **State machine governs phase transitions** — PHASE_DISCOVERY → PHASE_RESEARCH → PHASE_DELIVERY → PHASE_VALIDATION → PHASE_SUBMISSION. Orchestrator's prompt gates which skills are relevant at each phase.

### What Resonated
- Agent Skills spec as standard format for capability extension
- "Skill-discovering agent" as the product differentiator, not just "5 agents talking to each other"
- 3-gate trust model (verify, vet, sandbox) before activating unknown skills
- Dynamic capability loading without redeploys or code changes
- Catalog-driven extensibility (users configure sources via `/config`)

### What Was Cut
- Fixed sub-agents as separate processes (too much operational complexity)
- Custom skill generation (post-hackathon feature)
- A2A protocol for all inter-agent communication (now only Orchestrator↔Wallet)
- Per-agent telemetry (consolidated under Orchestrator spans)

### Deepening Rounds
No formal deepening rounds — architecture emerged through iterative discussion about tradeoffs between simplicity (single agent) vs. security boundaries (separate Wallet service).

### Active Shaping
- User drove the Agent Skills insight from the start
- User recognized dynamic skill discovery as the "wow factor" vs. just architectural preference
- User pushed back on scope creep — custom skill generation explicitly deferred
- User prioritized security (3-gate trust model) over convenience

## /prd

### What the learner added or changed vs the scope doc
- **Terminal UI layout specified:** Main view (tasks, phases), side column (error details), bottom status (counts), prompt (slash commands) — learner made these decisions during PRD conversation
- **Email alert channel added:** Low-cost async alerts via SendGrid + IMAP polling for guardrail fires, skill approvals, out-of-funds alerts — learner wanted ability to intervene when not at terminal
- **Validation loop defined:** Agent can iterate up to 3 times (configurable) if validation finds architectural issues, with time/cost constraints enforced — learner emphasized quality over speed but with hard limits
- **Wallet service simplified:** Direct function imports with module isolation instead of REST API — learner prioritized security + simplicity over service architecture
- **Code execution sandbox:** LXC containers instead of Docker (lighter weight, Linux-first) — learner preferred performance over portability
- **Configuration approach:** .env file instead of interactive setup — learner wanted transparent, file-based config

### What "what if" questions surprised them
- **Empty states:** Learner hadn't considered what happens when there are zero tasks, zero bids — we added explicit empty state handling
- **Skill discovery UX:** Learner hadn't specified whether agent blocks waiting for skill approval or continues with other tasks — we decided agent should continue
- **Guardrail override:** Learner hadn't considered whether user can override guardrail fires — we added explicit override flow with confirmation
- **Iteration limits:** Learner hadn't specified how many validation retry loops are allowed — we set default of 3 with .env override

### What they pushed back on or felt strongly about
- **Architecture quality matters:** Learner emphasized that deliverables shouldn't just meet spec, they should demonstrate good architecture (code structure, testing, modern tools) — this became a validation criterion
- **Non-interrupting commands:** Learner was strong about user commands not disrupting async agent work — we specified command queue + possible dedicated support agent
- **Wow moments:** Learner clearly prioritized skill discovery + security model as the two wow moments for Devpost — observability is nice but not the primary differentiator

### How scope guard conversations went
- **Custom skill generation deferred:** Learner recognized this would expand scope significantly — explicitly cut as post-hackathon feature
- **Advanced time estimation deprioritized:** Learner accepted heuristic-based approach for MVP, deferred ML-based learning
- **Multi-platform support cut:** Learner agreed to Linux-first design, cutting Windows/macOS to stay within 3-4 hour build window

### Deepening rounds
No formal deepening rounds — the conversation flowed as a single extended interview with iterative refinement. The learner provided detailed answers to all 15 question areas, with particular depth on edge cases (question 7), wallet service architecture (question 10), and email infrastructure (question A).

### Active shaping
- **Learner drove architectural decisions:** Wallet service as direct functions (not REST), LXC over Docker, .env config — these were all learner's choices, not suggestions
- **Learner challenged the "support agent" idea:** Questioned whether a separate agent is needed for user commands or if command queue suffices — we left this as an open question for /spec
- **Learner prioritized security over convenience:** 3-gate trust model, guardrail overrides requiring confirmation, credential isolation — all learner's emphases
- **Learner recognized email as critical channel:** Added email alerts + command replies unprompted — recognized async intervention as essential for production use

## /spec

### Technical decisions made and rationale
- **Terminal UI:** `textual` framework chosen over raw ANSI codes — provides structured regions, scrollable overlays, color support without reinventing the wheel
- **State management:** All state in SQLite (tasks, skills, review queue). No file-based JSON unless binary blobs emerge. Disk is source of truth for durability.
- **LLM abstraction:** Provider-agnostic interface — OpenRouter first, but architecture supports local LLM adapters (Ollama, vLLM) via same API contract
- **Guardrails:** Direct function imports (not separate processes) — simplifies deployment, reduces inter-process communication overhead. Synchronous calls block before LLM processing.
- **Email:** IMAP-only polling (every 60s), no SendGrid dependency. Agent never replies via email, only polls for commands. Idempotency via tracking email message IDs.
- **Skill format:** SKILL.md files for instructions + optional Python modules in `src/skills/`. Orchestrator reads SKILL.md for context, calls Python functions directly.
- **Time estimation:** LLM-as-estimator — call 3 times, take average of `estimated_minutes`. Later: factor in historical data by task owner, category, complexity.
- **Validation:** LLM-as-judge checks both acceptance criteria compliance AND architectural quality confidence. Configurable threshold (default 0.8). If only quality fails after 3 iterations, submit anyway with note.
- **Retry strategy:** `tenacity` with exponential backoff + jitter (2^0 through 2^4 = 1s, 2s, 4s, 8s, 16s). Max 5 attempts. After 5 failures: halt task, alert user.
- **Submission format:** Prefer `result_url` (GitHub Gist for small code, repo for larger projects). Use `result_content` only for single-file deliverables.

### What the learner was confident about vs uncertain
- **Confident:** SQLite for state, provider-agnostic LLM, package manager (`uv`), retry library (`tenacity`), terminal UI approach (TUI framework), deployment (local-only with screenshots)
- **Uncertain initially:** Skill execution model (scripts vs. instructions-only), guardrail architecture (separate processes vs. direct imports), email channel (SendGrid+IMAP vs. IMAP-only), validation exit criteria

### Stack choices and why
- `textual` over `rich` — provides full TUI app framework with regions, scrolling, overlays. `rich` is display-only.
- `uv` over `pip/poetry` — modern Python package management, faster dependency resolution
- `tenacity` over `stamina` — more customizable retry policies, better control over backoff strategy
- IMAP-only email — simplifies architecture (no SendGrid dependency), agent just polls for commands
- Direct function imports for wallet + guardrails — simpler than HTTP services for single-process architecture

### Deepening rounds
**2 deepening rounds conducted:**

**Round 1** covered 5 areas:
1. State management — SQLite for everything, disk as source of truth
2. Skill execution model — SKILL.md + optional Python modules
3. Guardrail architecture — changed from separate processes to direct function imports
4. Email IMAP polling — 60s interval, no SendGrid, agent polls for commands
5. Validation loop — LLM-as-judge for criteria + quality, configurable threshold, submit after max iterations even if only quality fails

**Round 2** covered 4 areas:
1. Task filtering — only `status=open`, prefer harder tasks, no minimum price
2. Time estimation — LLM heuristic, 3 calls averaged, future historical data
3. Submission format — prefer `result_url` (Gist/repo), content for single files
4. Error recovery — `tenacity`, 5 attempts, exponential backoff + jitter
5. Terminal UI layout — all tasks in main view, errors+info in side column, slash commands as scrollable overlay

Deeper specification caught architecture issue: **guardrail service design changed mid-conversation** from separate processes to direct function imports. This was a critical simplification that would have caused problems in `/build` if not resolved. Also clarified that skills are not just markdown — they have corresponding Python modules.

### Active shaping
- **Learner made key architecture decisions:** Guardrails changed from separate processes to direct imports (simplification), email simplified to IMAP-only (dropped SendGrid), state management consolidated to SQLite (no hybrid JSON approach)
- **Learner pushed back on complexity:** Questioned whether scripts in skills were necessary, favored simpler function-call architecture over separate services
- **Learner brought technical ideas:** LLM-as-estimator for time (3 calls averaged), LLM-as-judge for validation, idempotency via email message ID tracking, confidence threshold for architectural quality
- **Learner prioritized simplicity:** Direct imports over HTTP services, local-only deployment, terminal-only UI (no web dashboard)
