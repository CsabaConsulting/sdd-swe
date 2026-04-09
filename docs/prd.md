# Aegis — Product Requirements

## Problem Statement

Autonomous freelance agents on UpMoltWork face three critical failures: (1) They operate as opaque black boxes — users can't see what the agent is doing, why it made decisions, or when it encounters problems. (2) They execute without safety guardrails — credentials leak to LLMs, prompt injections go undetected, and malicious code runs unsandboxed. (3) They have fixed capabilities — built-in skills only, unable to adapt to new task types without redeploys.

Aegis solves this by providing an autonomous agent with dynamic skill discovery, end-to-end observability, and 3-gate security verification. The user can trust the agent's decisions (visible reasoning, audit trails), intervene when needed (guardrail alerts, halt commands), and leverage new capabilities autonomously (catalog-driven skill loading).

## User Stories

### Epic: System Observability

- As a system operator, I want to see the agent's task discovery and bidding decisions in real-time so that I can trust the autonomous behavior and verify it's acting in my best interest.
  - [ ] Main terminal view shows discovered tasks with title, points, deadline, and agent's bid confidence score
  - [ ] Tasks are sorted by priority (reputation risk + skill fit + points-to-effort ratio)
  - [ ] When agent places a bid, the task status updates to show "BIDDING: X points, est. Y min"
  - [ ] When a bid is won, the task moves to "IN PROGRESS" with phase indicator visible
  - [ ] Terminal shows which skill is currently active (e.g., "Active skill: bidding-strategy → code-delivery")
  - [ ] Edge case: When there are zero tasks available, terminal shows "Waiting for tasks..." with last refresh timestamp

- As a system operator, I want to watch the agent progress through work phases so I know where it is in the delivery lifecycle.
  - [ ] Phase indicator shows current phase: DISCOVERY → RESEARCH → DELIVERY → VALIDATION → SUBMISSION
  - [ ] During DELIVERY phase, terminal displays metrics: lines of code written, number of file edits, sub-specifications fulfilled
  - [ ] When phase transitions, a log entry is added with timestamp and reason for transition
  - [ ] Edge case: If agent cycles between phases (e.g., VALIDATION → DELIVERY → VALIDATION), the terminal shows iteration count

- As a system operator, I want to run slash commands without interrupting the agent's async work so I can check status on-demand.
  - [ ] Slash command output appears below the prompt area without disrupting the main task display
  - [ ] Commands queue if the agent is mid-operation, execute when agent is idle
  - [ ] User can scroll back through previous command outputs (terminal history preserved)
  - [ ] Available commands: `/status`, `/skills`, `/tasks`, `/review`, `/balance`, `/trace <id>`, `/halt <id>`, `/config`

- As a system operator, I want to see error alerts (guardrail fires, skill verification failures) in a dedicated area so I can identify issues immediately.
  - [ ] Side column shows guardrail/skill failure details (not just counts)
  - [ ] Bottom status line shows summary counts: "Errors: 2 unviewed | Guardrail fires: 1 | Skills loaded: 5"
  - [ ] Running `/review` displays full error details: phase/task context, flagged content snippet, recommended action
  - [ ] User can dismiss errors as "viewed" which decrements the unviewed count
  - [ ] Edge case: When side column is empty, it shows "No errors" placeholder

### Epic: Skill Discovery & Management

- As a system operator, I want to see when the agent discovers and loads new skills so I can verify it's extending its capabilities appropriately.
  - [ ] When Orchestrator loads a skill, terminal shows: "Skill loaded: <name> (source: <catalog URL>, phase: <phase name>)"
  - [ ] When Orchestrator unloads a skill, terminal shows: "Skill unloaded: <name> (reason: phase transition)"
  - [ ] Running `/skills` lists all available skills: built-in + cached, with last activation time and task associations
  - [ ] Running `/skill <name>` shows deep details: description, source catalog, verification status (checksum, vetting result, sandbox log)
  - [ ] Edge case: If skill discovery finds no matching skills, terminal shows "No skills found in catalogs for keywords: <keywords>"

- As a system operator, I want new skills to require approval before activation so that I can prevent malicious code from running.
  - [ ] First-time skill downloads pause skill activation (not task execution — agent moves to next task)
  - [ ] Skill approval request appears in error queue with details: name, description, source, vetting result
  - [ ] User can approve via `/approve <skill-name>` in terminal or by replying to email alert with `/approve <skill-name>`
  - [ ] Once approved, skill is cached and activated immediately if task is still active
  - [ ] Edge case: If user rejects skill, it's added to blocklist and never downloaded again

- As a system operator, I want the agent to continue working while waiting for skill approval so that productivity isn't blocked.
  - [ ] When skill approval is pending, agent skips to next highest-priority task
  - [ ] Once skill is approved, agent re-evaluates whether to return to the original task
  - [ ] No tasks are abandoned solely due to missing skills — agent always finds alternative work

### Epic: Security & Safety

- As a system operator, I want guardrails to filter all inbound and outbound content so that prompt injections and malicious outputs are caught.
  - [ ] All LLM inputs pass through Llama Prompt Guard (<10ms screening) before processing
  - [ ] All LLM outputs pass through Llama Guard (deep taxonomy classification) before execution
  - [ ] When guardrail fires, task is immediately halted, alert sent via email + terminal, task moved to review queue
  - [ ] User can review guardrail alert via `/review` and override via `/approve <task-id>` (terminal or email reply)
  - [ ] Guardrail override requires explicit confirmation: "Are you sure? This will bypass security. Confirm: /force-approve <id>"
  - [ ] Edge case: If guardrail service is down (network error), agent halts all tasks and alerts user

- As a system operator, I want credentials isolated from the LLM context so that API keys are never leaked to the agent.
  - [ ] Wallet credentials (UpMoltWork API key) stored in environment variables, accessed only by wallet_client.py module
  - [ ] Orchestrator calls wallet functions directly (no REST API), credentials never exposed to LLM context
  - [ ] Wallet module uses module isolation: `import wallet_client; wallet_client.place_bid(...)` — no direct key access by Orchestrator
  - [ ] Guardrail service also isolated — ML models run in separate containers, credentials in env vars

- As a system operator, I want code execution sandboxed so that malicious task inputs or LLM-generated code can't harm the system.
  - [ ] All code execution (tests, validation) runs in ephemeral LXC containers (lighter than Docker, Linux-first)
  - [ ] Containers have network disabled, filesystem restricted to read-only, destroyed after execution
  - [ ] If sandbox execution fails (timeout, crash, network call attempt), task is halted and user alerted
  - [ ] Edge case: If LXC is not available on the system, agent falls back to local execution with warning

### Epic: Bidding & Task Execution

- As a system operator, I want the agent to autonomously bid on tasks so that I can earn points without manual intervention.
  - [ ] Agent uses zero-shot defaults for bidding strategy: min points-to-effort ratio, max bid amount, confidence threshold
  - [ ] Agent learns from past bids: adjusts strategy based on win rate, points earned, time spent
  - [ ] Before placing bid, agent checks if competitor agents are bidding (if API provides this data — currently not available)
  - [ ] Bid includes: `price_points`, `estimated_minutes` (from wallet service heuristic), `proposed_approach` (LLM-generated)
  - [ ] Edge case: If balance is zero, agent halts bidding and sends email alert

- As a system operator, I want the agent to abandon tasks it can't complete so that reputation isn't damaged by partial submissions.
  - [ ] If agent lacks required skills and discovery fails, it abandons task and signals inability to complete (if API supports)
  - [ ] If agent hits time/cost limit from bid, it relaxes nice-to-haves but never submits incomplete work
  - [ ] If UpMoltWork API supports deadline extensions, agent requests extension before abandoning
  - [ ] If task must be abandoned, agent logs reason and moves to next task
  - [ ] Edge case: If API doesn't support "unable to complete" signal, agent just stops working on task and moves on

- As a system operator, I want the agent to iterate on deliverables based on validation feedback so that quality improves before submission.
  - [ ] Validation skill checks architecture quality (code structure, best practices, cyclomatic complexity) + spec compliance
  - [ ] If validation fails, it provides specific recommendations to `code-delivery` skill
  - [ ] Agent iterates up to `MAX_VALIDATION_ITERATIONS` times (default 3, configurable in .env)
  - [ ] If iterations exhausted but deliverable still has architecture issues, agent submits anyway with note about compromises
  - [ ] Edge case: If time/cost limit is reached during iteration, agent submits current state with "architecture incomplete" flag

- As a system operator, I want email alerts for critical events so that I can intervene even when not at the terminal.
  - [ ] Email sent via SendGrid (free tier) for: guardrail fires, skill approval needed, out of funds, agent crash
  - [ ] Email format: plain text with structured sections (parseable) + descriptive subject line (SPAM-resistant)
  - [ ] User can reply to email with commands: `/approve <skill-name>`, `/halt <task-id>`, `/force-approve <task-id>`
  - [ ] Agent polls Gmail inbox via IMAP every 5 minutes for command replies
  - [ ] Edge case: If email service is down, agent logs alert locally and continues

### Epic: Configuration & Setup

- As a system operator, I want to configure the system via .env file so that setup is simple and transparent.
  - [ ] Required env vars: `UPMOLTWORK_API_KEY`, `OPENROUTER_API_KEY`, `SENDGRID_API_KEY`, `IMAP_HOST`, `IMAP_USER`, `IMAP_PASS`
  - [ ] Optional env vars: `VALIDATION_CONFIDENCE_THRESHOLD` (default 0.8), `MAX_VALIDATION_ITERATIONS` (default 3), `GUARDRAIL_MODEL_PATH`
  - [ ] Agent validates API keys on startup (test calls to UpMoltWork + OpenRouter)
  - [ ] If env vars missing, agent shows clear error: "Missing UPMOLTWORK_API_KEY — set in .env file"
  - [ ] Edge case: If OpenRouter is down, agent falls back to local LLM (if configured) or halts

- As a system operator, I want to monitor points balance and transfer history so that I can track earnings.
  - [ ] Running `/balance` shows: current points balance, USDC balance, recent transfers (from `GET /points/balance`)
  - [ ] Agent automatically tracks earnings per completed task
  - [ ] If balance reaches zero, agent halts bidding and sends email alert
  - [ ] Edge case: If balance API call fails, agent retries 3 times then alerts user

## What We're Building

Everything in the user stories above with acceptance criteria. This is the complete scope for a 3-4 hour build.

**Core features (must-have):**
- Terminal UI with main view (tasks, phases), side column (errors), bottom status (summary), prompt (commands)
- Orchestrator with dynamic skill loading (5 built-in skills + cache for downloaded skills)
- Skill discovery pipeline: search catalogs, 3-gate verification (checksum, skill-vetting, sandbox), human approval
- Wallet module (direct function imports) for UpMoltWork API calls: bidding, balance, submission
- Guardrail services (Prompt Guard + Llama Guard) filtering all LLM inputs/outputs
- Code execution sandbox (LXC containers) for all code deliverables
- Email alerts via SendGrid for critical events, IMAP polling for command replies
- OpenTelemetry tracing for all LLM calls, tool calls, phase transitions, skill activations
- Configuration via .env file with validation on startup

## What We'd Add With More Time

- **Advanced time estimation**: ML-based model for predicting task duration based on complexity, code size, historical data (currently heuristic-only)
- **Multi-platform support**: Windows and macOS compatibility (currently Linux-first, LXC-specific)
- **Custom skill generation**: Agent generates new SKILL.md files from scratch based on task requirements (currently only downloads from catalogs)
- **Advanced competition tracking**: If UpMoltWork API adds competitor bid data, use it to refine bidding strategy
- **Web UI alternative to terminal**: Browser-based admin dashboard for users who prefer GUI (currently terminal-only)
- **Real-time collaboration**: Multi-user terminal access with role-based permissions (currently single operator)
- **Deadline extension requests**: If UpMoltWork API adds extension endpoint, implement automatic extension logic
- **Learning model for bidding**: Train on historical bid data to improve win rate (currently heuristic + simple feedback loop)

## Non-Goals

- **Web UI for the system itself** — The terminal + Phoenix web UI provides full observability. No separate admin dashboard needed. (Rationale: Keeps scope tight, terminal is sufficient for Devpost demo.)

- **Custom skill generation during hackathon** — Aegis will discover and download skills, but won't generate new SKILL.md files from scratch. (Rationale: Skill generation is complex, post-hackathon feature.)

- **Multi-platform support (Windows/macOS)** — Linux-first design with LXC containers. (Rationale: Simplifies development, aligns with target deployment.)

- **Automatic guardrail override** — Guardrail fires require human review. No auto-bypass. (Rationale: Security-by-design, prevents malicious tasks from slipping through.)

- **Real-time collaboration** — No multi-user terminal access. Single operator. (Rationale: Complexity not justified for solo hackathon project.)

- **Deadline extension via API** — Not supported by UpMoltWork API currently. (Rationale: API doesn't expose extension endpoint.)

- **Browser automation / web scraping** — If UpMoltWork requires non-API interaction, that's out of scope. API-only. (Rationale: Adds significant complexity, API should be sufficient.)

- **Advanced time estimation learning** — Heuristic-based only for now. No ML model for task duration prediction. (Rationale: Heuristics sufficient for MVP, learning is optimization.)

## Open Questions

**Before /spec (must be answered):**
- What are the exact environment variable names for SendGrid API key, IMAP credentials? (User will define in .env)
- What's the precise LXC container setup command? (User will decide in /spec)
- What OpenTelemetry attributes should be included in traces? (User will specify, but should include: task_id, phase, skill_name, LLM model, token_count, latency)

**Can wait until build time:**
- What's the exact email subject line format? (e.g., "🚨 Aegis Alert: Guardrail Fired on Task XYZ" — user will decide)
- What's the precise directory structure for cached skills? (e.g., `.agents/skills/cache/<name>/SKILL.md` vs alternative)
- What's the fallback if LXC is not available? (Local execution with warning, or halt?)
