# Aegis — Autonomous Freelance Agent

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)

Aegis is a guarded, skill-discovering autonomous agent for the UpMoltWork marketplace. It monitors tasks, bids intelligently, executes deliverables with security guardrails, and extends its own capabilities by discovering new skills from online catalogs.

## Key Features

- **Dynamic Skill Discovery:** Autonomously searches online catalogs, evaluates relevance, downloads + verifies + sandboxes new skills with 3-gate trust model
- **3-Gate Security:** Prompt Guard (<10ms screening) + Llama Guard 3 (deep taxonomy) + sandboxed execution for 3rd party skills
- **Credential Isolation:** API keys stored in env vars, accessed only by wallet client — never exposed to LLM context
- **Full Observability:** OpenTelemetry tracing for all LLM calls, phase transitions, skill activations — self-hosted Phoenix UI
- **Retro Terminal UI:** Textual-based TUI with 4 regions (tasks, errors, status, commands) and slash command interface

## Architecture

```
Orchestrator Engine (State Machine)
├── PHASE_DISCOVERY → bidding-strategy
├── PHASE_RESEARCH → research
├── PHASE_DELIVERY → code-delivery
├── PHASE_VALIDATION → validation
└── PHASE_SUBMISSION → wallet-management

Supporting Services:
├── Guardrails: Prompt Guard + Llama Guard 3 (direct imports)
├── Wallet: UpMoltWork API client with tenacity retries
├── Sandbox: LXC containers for code execution
├── Skills: 5 built-in + dynamic cache + 3-gate vetting
└── State: SQLite (tasks, skills, review queue, command log)
```

## Quick Start

```bash
# 1. Install dependencies
uv sync

# 2. Configure credentials
cp .env.example .env
# Edit .env with your API keys

# 3. Run the agent
uv run python -m src.cli.ui
```

## Configuration

See `.env.example` for all available options:

| Variable | Required | Description |
|----------|----------|-------------|
| `UPMOLTWORK_API_KEY` | Yes | UpMoltWork marketplace API key |
| `OPENROUTER_API_KEY` | Yes | OpenRouter API key for LLM access |
| `IMAP_HOST` | Yes | IMAP server for command polling |
| `IMAP_USER` | Yes | IMAP username/email |
| `IMAP_PASS` | Yes | IMAP password/app password |
| `VALIDATION_CONFIDENCE_THRESHOLD` | No | Min quality confidence (default: 0.8) |
| `MAX_VALIDATION_ITERATIONS` | No | Max validation retries (default: 3) |
| `SPECIALIZATIONS` | No | Comma-separated task categories |

## Slash Commands

| Command | Purpose |
|---------|---------|
| `/status` | Overall system status, current phase |
| `/skills` | List all available skills |
| `/tasks` | Active tasks with status |
| `/review` | Halted tasks awaiting review |
| `/balance` | Points and USDC balance |
| `/trace <id>` | Phoenix trace deep link |
| `/halt <id>` | Halt a running task |
| `/config` | System configuration |

## Project Structure

```
sdd-swe/
├── src/
│   ├── cli/              # Terminal UI (Textual)
│   ├── orchestrator/     # State machine engine
│   ├── skills/           # Skill management
│   ├── guardrails/       # Security pipeline
│   ├── wallet/           # API client
│   ├── execution/        # LXC sandbox
│   ├── alerts/           # Email polling
│   ├── config/           # .env loader
│   └── db/               # SQLite store
├── skills/               # Built-in SKILL.md files
├── docs/                 # Scope, PRD, spec, checklist
└── tests/                # Unit + integration tests
```

## How It Works

1. **Discovery:** Orchestrator scans `/tasks`, bidding strategy evaluates fit, places bids
2. **Research:** When bid won, research skill investigates requirements
3. **Delivery:** Code delivery skill generates solution, tests in sandbox
4. **Validation:** LLM-as-judge checks acceptance criteria + architectural quality
5. **Submission:** Wallet client submits result, earns points, returns to discovery

## Security Model

- **3-Gate Skill Verification:** Checksum → Heuristic Scan → Sandbox → Human Approval
- **Guardrails:** All LLM inputs/outputs filtered through Prompt Guard + Llama Guard 3
- **Credential Isolation:** API keys in env vars, never exposed to LLM
- **Sandboxed Execution:** All code runs in ephemeral LXC containers (network disabled, read-only FS)

## Tech Stack

- **Language:** Python 3.12+
- **Terminal UI:** Textual 0.80+
- **Package Manager:** uv
- **State:** SQLite (aiosqlite)
- **LLM:** OpenRouter (provider-agnostic interface)
- **Retries:** tenacity (exponential backoff + jitter)
- **Tracing:** OpenTelemetry + Phoenix (self-hosted)

## License

MIT

## Acknowledgments

Built with [Claude Code](https://claude.ai/code) for the [UpMoltWork](https://upmoltwork.mingles.ai/) hackathon. Architecture designed with Spec-Driven Development methodology.
