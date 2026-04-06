# Aegis — Autonomous Freelance Agent System

## Idea

A guarded, multi-agent system that autonomously discovers, bids on, and delivers work on the UpMoltWork marketplace — with safety-first guardrails at every stage and real-time observability through distributed tracing.

## Who It's For

Primary user: a solo operator or small team who wants to deploy an autonomous "team" of LLM-powered agents to earn points and USDC on UpMoltWork. The system represents a single entity on the platform, with one orchestrator managing specialized sub-agents.

The platform community: other agents and human participants who interact with submissions, validate deliverables, and vote on quality.

## Inspiration & References

- **AGNTCY coffeeAgntcy workshops** ([GitHub](https://github.com/agntcy/coffeeAgntcy/tree/main/coffeeAGNTCY/coffee_agents)) — P2P async agent-to-agent communication patterns; corto, lungo, and recruiter workshops informed the orchestrator/sub-agent delegation model.
- **Google A2A Protocol** — agent cards, async bidirectional messaging, discoverable agents.
- **UpMoltWork API** ([docs](https://api.upmoltwork.mingles.ai/v1/openapi.json)) — full REST API with agent registration, task discovery, bidding, submission, validation, and points economy.
- **Llama Prompt Guard** — extremely fast input screening, first-line defense.
- **Llama Guard 3** (MLCommons taxonomy) — deeper content classification for both inbound and outbound.

Design energy: clean, functional, developer-tool aesthetic. Retro terminal with color support. Linux-first.

## Goals

- Build a **supervised-autonomy** multi-agent system for freelance work — autonomous by default, interruptible on guardrail alert.
- Demonstrate that A2P-style P2P orchestrator/sub-agent architecture works reliably for end-to-end task delivery.
- Achieve **security-by-design**: no credentials leaked to LLMs, prompt-injection resistant, content-safe outbound.
- Provide **full observability**: every action is traced, every guardrail firing is logged, every task is auditable — via OpenTelemetry + self-hosted Phoenix.
- Support **multiple LLM backends**: local (Ollama, SGLang, vLLM, TensorRT) or cloud (OpenRouter), user-configurable.
- Deliver something compelling enough to earn points and climb the UpMoltWork leaderboard.

## Architecture Overview

### Agents (all P2P, async, with A2A agent cards)

| Agent | Responsibility |
|-------|----------------|
| **Orchestrator** | Scans `/tasks`, evaluates fit, delegates to sub-agents, manages task lifecycle, represents the system on UpMoltWork |
| **Coder** | Development tasks — writes, tests, and packages code deliverables |
| **Researcher** | Content, marketing, analytics tasks — web search, writing, analysis |
| **Validator** | Pre-submission quality check against acceptance criteria |
| **Wallet** | API key vault, bidding, points management, P2P transfers, time estimation (heuristic-based) |

Agents communicate via direct HTTP (P2P), each managing its own message queue/state. No shared event bus. The Orchestrator is the coordinator but agents are independently discoverable and executable.

### Guardrail Pipeline (two-tier)

1. **Llama Prompt Guard** — fast (<10ms) screening on all inbound content. Blocks obvious injection before agent processes it.
2. **Llama Guard 3** — deeper MLCommons taxonomy-based classification on both inbound and outbound content. Flags nuanced threats.

On guardrail fire: task is **halted**, alert pushed to terminal, task moved to **review queue**, agent freed to bid on next task. System does not auto-retry — requires human review.

### Credential Security

- API keys stored encrypted, accessed only by the **Wallet** agent
- Credentials never passed to LLM context
- Outbound content guard checks for credential patterns (64-hex strings matching `axe_agent_id_*` format)
- Sub-agents proxy credential-dependent actions through Wallet — never hold keys

### Telemetry / Observability

- **OpenTelemetry Protocol (OTel)** for distributed tracing across all agents
- **Phoenix (Arize)** — self-hosted Docker container, web UI for traces/spans/sessions
- Correlation: each UpMoltWork task maps to a `task_context_id`, propagated via `traceparent` headers in all P2P messages
- Terminal provides deep links into Phoenix UI (`http://localhost:6006/trace/{trace_id}`)

## What "Done" Looks Like

After the development period:

- A fully integrated system that registers on UpMoltWork, continuously monitors `/tasks`, evaluates task suitability, places bids, and upon acceptance executes deliverables end-to-end.
- Five specialized agents running as separate processes/containers, communicating via P2P async with A2A-compatible agent cards.
- Two-layer guardrail pipeline active on every inbound and outbound message, with automatic halt-and-review on alerts.
- Phoenix tracing every action — from task discovery through guardrail checks to submission — with session replay and deep-linkable traces.
- Retro terminal CLI: see all agents, their status, current tasks, guardrail alerts, points balance, and review queue. Slash commands for control and monitoring.
- Configurable LLM backend: start with OpenRouter, architecture supports swapping to local providers.
- System has earned points on the platform, with traceable evidence of guardrails in action.
- Open-source with documentation covering architecture, security model, and deployment.

## Slash Commands

| Command | Purpose |
|---------|---------|
| `/status` | Overall system status, all agents at a glance |
| `/agents` | List all sub-agents, their current state, and what they're working on |
| `/tasks` | Active tasks, pending bids, review queue |
| `/agent <name>` | Deep dive into a specific agent's history and achievements |
| `/trace <id>` | Get deep link to Phoenix trace for a specific task |
| `/review` | Show halted tasks awaiting review, with guardrail alert details |
| `/approve <id>` / `/reject <id>` | Manual review queue actions |
| `/balance` | Points and USDC balance, recent transfers |
| `/halt <task>` | Manually halt a running task |
| `/bid <strategy>` | Configure bidding strategy |
| `/config` | System configuration (LLM backend, guardrail settings) |
| `/leaderboard` | UpMoltWork public leaderboard |
| `/logs <agent>` | Recent action log for a specific agent |

## What's Explicitly Cut

Named features, use cases, or scope that is OUT. With brief rationale.

- **Web UI for the system itself** — the terminal + Phoenix web UI provides full observability. No separate admin dashboard.
- **Multi-platform support** — Linux-first. No Windows or macOS supportability guarantees.
- **Dynamic sub-agent spawning** — agents are pre-defined (coder, researcher, validator, wallet). No runtime creation of new agent types.
- **Browser automation / web scraping** — if UpMoltWork requires non-API interaction, that's out of initial scope. API-only.
- **Automatic guardrail override** — guardrail fires require human review. No auto-bypass.
- **Non-UpMoltWork platform integration** — single platform initially. Architecture may support multiple marketplaces later.
- **Real-time collaboration** — no multi-user terminal access. Single operator.
- **Advanced time estimation** — heuristic-based only for now. No learning model for task duration prediction.

## Loose Implementation Notes

Early thinking on approach. Non-binding. Gets refined in /spec.

- **Language:** Python for all agents. Terminal CLI in Python (rich/click).
- **Communication:** HTTP-based P2P with A2A protocol. Each agent exposes an endpoint, registers an A2A agent card. Message payloads include `traceparent` headers for trace correlation.
- **LLM abstraction layer:** Provider-agnostic interface. OpenRouter first, then Ollama/SGLang/vLLM adapters.
- **Guardrail deployment:** Both Llama Prompt Guard and Llama Guard run as local services (Docker or local model loading). Fast guard (~10ms) always runs first; slow guard runs in parallel or shortly after.
- **Task execution sandbox:** Code execution by the Coder agent should happen in an isolated container (D-in-D or Firecracker) to prevent supply-chain attacks from task inputs.
- **Database:** Lightweight (SQLite or DuckDB) for local state per agent. Phoenix handles its own persistence.
- **Tailscale connectivity:** Each agent is accessible via Tailscale IP. The terminal connects locally. Phoenix UI accessible via Tailscale.
- **Idempotency:** UpMoltWork API requires Idempotency-Key on transfers. All agent actions should be idempotent.
- **Testing strategy:** Unit tests for guardrail logic, integration tests for agent communication, end-to-end test cycle with mock UpMoltWork server.
