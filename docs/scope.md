# Aegis — Autonomous Freelance Agent System

## Idea

A guarded, skill-discovering autonomous agent system that operates on the UpMoltWork marketplace — with safety-first guardrails at every stage and real-time observability through distributed tracing.

Core innovation: Instead of a fixed set of sub-agents, Aegis uses an Orchestrator that dynamically loads/unloads specialized skills (`.agents/skills/SKILL.md` files) based on task phase. When no built-in skill fits, the Orchestrator autonomously searches online agent-skill catalogs, evaluates matches, and downloads new skills with full trust verification.

## Who It's For

Primary user: a solo operator or small team who wants to deploy an autonomous agent to earn points and USDC on UpMoltWork. The system represents a single entity on the platform, with one orchestrator dynamically adapting its capabilities.

The platform community: other agents and human participants who interact with submissions, validate deliverables, and vote on quality.

## Inspiration & References

- **Agent Skills specification** ([agentskills.io](https://agentskills.io)) — Standard SKILL.md format with progressive disclosure (catalog → instructions → resources). Enables dynamic capability loading.
- **AGNTCY coffeeAgntcy workshops** ([GitHub](https://github.com/agntcy/coffeeAgntcy/tree/main/coffeeAGNTCY/coffee_agents)) — P2P async agent-to-agent communication patterns informed the Orchestrator↔Wallet service design.
- **UpMoltWork API** ([docs](https://api.upmoltwork.mingles.ai/v1/openapi.json)) — Full REST API with agent registration, task discovery, bidding, submission, validation, and points economy.
- **awesome-agent-skills catalogs** — heilcheng, CommandCodeAI, MoizIbnYousaf, Copilot skills — Real-world examples of skill granularity and organization patterns.
- **Llama Prompt Guard** — Extremely fast input screening (<10ms), first-line defense against prompt injection.
- **Llama Guard 3** (MLCommons taxonomy) — Deeper content classification for both inbound and outbound.

Design energy: clean, functional, developer-tool aesthetic. Retro terminal with color support. Linux-first.

## Goals

- Build a **skill-discovering autonomous agent** for freelance work — autonomous by default, interruptible on guardrail alert.
- Demonstrate that the **Agent Skills protocol** enables dynamic capability extension without redeploys or code changes.
- Achieve **security-by-design**: no credentials leaked to LLMs, prompt-injection resistant, content-safe outbound, 3rd party skill vetting.
- Provide **full observability**: every action is traced, every skill activation logged, every guardrail firing auditable — via OpenTelemetry + self-hosted Phoenix.
- Support **multiple LLM backends**: local (Ollama, SGLang, vLLM, TensorRT) or cloud (OpenRouter), user-configurable.
- Ship with 5 built-in skills optimized for UpMoltWork workflow (bidding-strategy, research, code-delivery, validation, wallet-management).
- Implement **dynamic skill discovery** — autonomously search online catalogs, evaluate matches, download + verify + sandbox new skills.
- Deliver something compelling enough to earn points and climb the UpMoltWork leaderboard.

## Architecture Overview

### The Orchestrator (Single Python Process)

The Orchestrator is the only LLM-powered agent. It operates as a finite state machine with phases:

| Phase | Trigger | Active Skill | Unloaded Skills |
|-------|---------|--------------|-----------------|
| PHASE_DISCOVERY | Scanning `/tasks` | bidding-strategy | All others |
| PHASE_RESEARCH | Task accepted, needs investigation | research | bidding-strategy |
| PHASE_DELIVERY | Task ready for execution | code-delivery OR domain-specific skill | research |
| PHASE_VALIDATION | Deliverable ready for QA | validation | code-delivery |
| PHASE_SUBMISSION | Quality confirmed | wallet-management | validation |

**Progressive disclosure pattern:**
- **Tier 1 (catalog):** At startup, Orchestrator scans all available skills (built-in + cached), loads only `name` + `description` (~50-100 tokens per skill)
- **Tier 2 (instructions):** When phase changes, Orchestrator loads full SKILL.md body (<5000 tokens recommended)
- **Tier 3 (resources):** If SKILL.md references scripts/references, Orchestrator loads them on-demand via file-read

**Context management:** Only 1-2 skills active at any time. Orchestrator explicitly unloads irrelevant skills during phase transitions. This prevents context bloat.

### Built-in Skills (Ship with Aegis)

| Skill | Responsibility | Phase | Location |
|-------|----------------|-------|----------|
| **bidding-strategy** | Scan `/tasks`, evaluate fit, calculate bid amount, place bids | PHASE_DISCOVERY | `skills/bidding-strategy/SKILL.md` |
| **research** | Web search, content analysis, writing, market research | PHASE_RESEARCH | `skills/research/SKILL.md` |
| **code-delivery** | Development tasks — writes, tests, packages code deliverables | PHASE_DELIVERY | `skills/code-delivery/SKILL.md` |
| **validation** | Pre-submission quality check against acceptance criteria | PHASE_VALIDATION | `skills/validation/SKILL.md` |
| **wallet-management** | Wallet HTTP client — bidding, points management, P2P transfers, time estimation | PHASE_SUBMISSION | `skills/wallet-management/SKILL.md` |
| **skill-vetting** | **Security skill** — examines 3rd party SKILL.md files for malicious intent, validates source reputation, checks for suspicious patterns | N/A (on-demand) | `skills/skill-vetting/SKILL.md` |

Each skill is a `SKILL.md` file with:
- YAML frontmatter: `name`, `description`, optional `compatibility` notes
- Markdown body: "When to use", "How to use", "Reference", "Safety notes"
- Optional bundled resources: `scripts/`, `references/`, `assets/`

### Dynamic Skill Discovery

When built-in skills don't match a task, Orchestrator autonomously searches online catalogs:

1. **Search phase:**
   ```
   Orchestrator → skills search "<task keywords>" against configured catalogs
   Catalog returns: skill name, description, ratings, last updated, source URL
   ```

2. **Evaluation phase:**
   ```
   Orchestrator ranks results by:
   - Relevance to task description
   - Source reputation (official catalog > community > unknown)
   - Last updated (recent > stale)
   - Star rating / download count
   ```

3. **Trust verification phase (3 gates):**
   ```
   Gate 1: Content-addressable verification
     - Download SKILL.md + checksum
     - Compare against catalog's known-good hash (if available)
     - Reject if mismatch
   
   Gate 2: skill-vetting skill activation
     - Load skill-vetting SKILL.md
     - Pass downloaded SKILL.md content through vetting agent
     - Check for: suspicious file operations, credential patterns, command injection, network exfiltration
     - If vetting fails → reject skill, log alert
   
   Gate 3: Sandboxed execution test (first-time only)
     - Execute skill's instructions against mock input in isolated Docker container
     - Monitor for: filesystem writes, network calls, unexpected behavior
     - If sandbox passes → cache skill in `.agents/skills/cache/<name>/`
     - If sandbox fails → reject skill, log alert
   
   Gate 4: Human approval (first-time only, configurable)
     - Push skill to review queue
     - Terminal shows: skill name, description, source, vetting result, sandbox log
     - User types `/approve <skill-name>` or `/reject <skill-name>`
   ```

4. **Activation phase:**
   ```
   If all gates pass:
     - Cache SKILL.md in `.agents/skills/cache/<name>/`
     - Load into Orchestrator context
     - Execute task with new skill
     - Unload after task completion (skill stays cached for future reuse)
   ```

**Configured catalogs (defaults in `/config`):**
- `github/heilcheng/awesome-agent-skills`
- `github/CommandCodeAI/agent-skills`
- `github/MoizIbnYousaf/Ai-Agent-Skills`
- `github/github/awesome-copilot/skills`

Users can add/remove catalogs via `/config` command.

### External Services (HTTP, No LLM)

Two services run as separate containers/processes for security and isolation:

#### Wallet Service (HTTP API)

Exposes endpoints for credential-dependent operations. **Not an LLM agent** — just a Flask/FastAPI service.

| Endpoint | Purpose | Notes |
|----------|---------|-------|
| `POST /bid` | Place bid on UpMoltWork | Validates strategy, checks balance, enforces rate limits |
| `POST /transfer` | Execute P2P transfer | Requires `Idempotency-Key` header, signs with API key |
| `GET /balance` | Query points + USDC balance | Returns current balance, recent transfers |
| `POST /estimate-time` | Heuristic-based duration estimate | Calculates task duration based on complexity, code size |

**Credential isolation:** Wallet service holds encrypted API keys. Keys are never exposed to LLM context. Orchestrator calls endpoints via `wallet_client.py` (imported by `wallet-management` skill).

#### Guardrail Service (ML Models, No LLM)

Two-layer pipeline, running as isolated services:

1. **Llama Prompt Guard** — Fast screening (<10ms) on all inbound content. Blocks obvious injection before Orchestrator processes it.
2. **Llama Guard 3** — Deep MLCommons taxonomy-based classification on inbound + outbound content. Flags nuanced threats.

On guardrail fire: task is **halted**, alert pushed to terminal, task moved to **review queue**, Orchestrator freed to bid on next task. System does not auto-retry — requires human review.

### Code Execution Sandbox

When `code-delivery` skill needs to run tests or validate code:
- Spin up ephemeral Docker-in-Docker container per task
- Mount code deliverable in read-only mode
- Execute tests with network disabled, filesystem restricted
- Collect outputs, destroy container
- Return results to Orchestrator

This prevents supply-chain attacks from malicious task inputs or LLM-generated code.

### Telemetry / Observability

- **OpenTelemetry Protocol (OTel)** for distributed tracing
- **Phoenix (Arize)** — Self-hosted Docker container, web UI for traces/spans/sessions
- Correlation: each UpMoltWork task maps to a `task_context_id`, propagated via `traceparent` headers in all HTTP requests (Wallet service, Guardrail service)
- Orchestrator phases traced as spans: `Orchestrator.PHASE_DISCOVERY`, `Orchestrator.PHASE_DELIVERY`, etc.
- Skill activation events traced: `skill.loaded`, `skill.unloaded`, `skill.discovered`, `skill.verified`
- Terminal provides deep links into Phoenix UI (`http://localhost:6006/trace/{trace_id}`)

## What "Done" Looks Like

After the development period:

- A fully integrated system that registers on UpMoltWork, continuously monitors `/tasks`, evaluates task suitability, places bids, and upon acceptance executes deliverables end-to-end.
- **One Orchestrator process** dynamically loading/unloading skills based on task phase.
- **5 built-in skills** (bidding-strategy, research, code-delivery, validation, wallet-management) + **1 security skill** (skill-vetting).
- **Dynamic skill discovery** active — autonomously searches configured catalogs, downloads + verifies + sandboxes new skills with 3-gate trust model.
- **Wallet HTTP service** isolating credentials — Orchestrator never sees API keys, all transfers go through signed HTTP requests.
- **Guardrail services** (Prompt Guard + Llama Guard) always-on, filtering inbound and outbound content.
- **Code execution sandbox** — all code deliverables run in ephemeral Docker containers, preventing supply-chain attacks.
- Phoenix tracing every action — from task discovery through skill activation to submission — with session replay and deep-linkable traces.
- Retro terminal CLI: see system status, loaded skills, active tasks, guardrail alerts, points balance, and review queue. Slash commands for control and monitoring.
- Configurable LLM backend: start with OpenRouter, architecture supports swapping to local providers.
- System has earned points on the platform, with traceable evidence of guardrails in action and skill discovery in practice.
- Open-source with documentation covering architecture, security model, skill discovery protocol, and deployment.

## Slash Commands

| Command | Purpose |
|---------|---------|
| `/status` | Overall system status, current phase, loaded skills |
| `/skills` | List all available skills (built-in + cached), their status, last activation time |
| `/tasks` | Active tasks, their phases, which skill is handling each |
| `/skill <name>` | Deep dive into a specific skill: description, source, last loaded, tasks associated |
| `/trace <id>` | Get deep link to Phoenix trace for a specific task |
| `/review` | Show halted tasks awaiting review, with guardrail alert details |
| `/approve <id>` / `/reject <id>` | Manual review queue actions (including skill approval) |
| `/balance` | Points and USDC balance, recent transfers (via Wallet service) |
| `/halt <task>` | Manually halt a running task |
| `/bid <strategy>` | Configure bidding strategy parameters |
| `/config` | System configuration (LLM backend, guardrail settings, skill catalog sources) |
| `/leaderboard` | UpMoltWork public leaderboard |
| `/logs` | Recent action log (phase transitions, skill activations, discovery events) |

## What's Explicitly Cut

Named features, use cases, or scope that is OUT. With brief rationale.

- **Web UI for the system itself** — the terminal + Phoenix web UI provides full observability. No separate admin dashboard.
- **Multi-platform support** — Linux-first. No Windows or macOS supportability guarantees.
- **Custom skill generation** — Post-hackathon feature. Aegis will discover and download skills, but won't generate new SKILL.md files from scratch.
- **Non-UpMoltWork platform integration** — Single platform initially. Architecture may support multiple marketplaces later.
- **Real-time collaboration** — No multi-user terminal access. Single operator.
- **Advanced time estimation** — Heuristic-based only for now. No learning model for task duration prediction.
- **Browser automation / web scraping** — If UpMoltWork requires non-API interaction, that's out of initial scope. API-only.
- **Automatic guardrail override** — Guardrail fires require human review. No auto-bypass.
- **Dynamic sub-agent spawning** — No runtime creation of separate agent processes. Capabilities are loaded as skills, not spawned as services.

## Loose Implementation Notes

Early thinking on approach. Non-binding. Gets refined in /spec.

- **Language:** Python for Orchestrator. Terminal CLI in Python (rich/click). Wallet service in Flask/FastAPI.
- **Skill format:** Agent Skills spec-compliant SKILL.md files. Progressive disclosure: catalog → instructions → resources.
- **LLM abstraction layer:** Provider-agnostic interface. OpenRouter first, then Ollama/SGLang/vLLM adapters.
- **Guardrail deployment:** Both Llama Prompt Guard and Llama Guard run as local services (Docker or local model loading). Fast guard (~10ms) always runs first; slow guard runs in parallel or shortly after.
- **Task execution sandbox:** Code execution by the `code-delivery` skill happens in an isolated Docker container to prevent supply-chain attacks from task inputs.
- **Database:** Lightweight (SQLite or DuckDB) for local state: task phases, skill cache metadata, review queue. Phoenix handles its own persistence.
- **Tailscale connectivity:** Orchestrator accessible via Tailscale IP for remote terminal access. Phoenix UI accessible via Tailscale.
- **Idempotency:** UpMoltWork API requires Idempotency-Key on transfers. All Wallet service actions should be idempotent.
- **Testing strategy:** Unit tests for guardrail logic, skill vetting, state machine transitions. Integration tests for skill discovery pipeline. End-to-end test cycle with mock UpMoltWork server.
- **Skill catalog caching:** Downloaded skills cached in `.agents/skills/cache/<name>/`. Cache invalidation: manual via `/config` or time-based (e.g., 30-day TTL).
