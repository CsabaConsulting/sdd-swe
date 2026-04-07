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
