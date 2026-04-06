# Process Notes

## /scope


### Conversation Flow
- User arrived with a well-formed idea: autonomous freelancing agent for UpMoltWork
- Initial scope: agentic system that bids/delivers on UpMoltWork, configurable LLM backend, terminal monitoring
- Evolved through conversation: added guardrails (two-tier: Prompt Guard + Llama Guard), P2P A2A communication inspired by coffeeAgntcy, telemetry with Phoenix/OTel, credential isolation
- Key decision: supervised autonomy (not full autonomy) — guardrails halt, human reviews
- Key decision: weeks of timeline, not 3-4 hours → plan boldly
- User initially mentioned Google ADK, then withdrew it
- Deepening rounds: 1 informal round — security architecture, terminal commands, telemetry system selection

### What Resonated
- AGNTCY coffeeAgntcy workshops as reference for P2P agent communication
- Phoenix (Arize) as self-hosted observability, with deep links from terminal
- Two-layer guardrail pipeline (fast + deep)
- Credential isolation via Wallet agent proxy pattern
- Retro terminal with Tailscale for remote access

### Active Shaping
- User drove the security-first framing heavily
- User pushed back on ADK, withdrew it quickly
- User contributed the guardrail taxonomy (Prompt Guard vs Llama Guard distinction)
- User provided the full OpenAPI spec for UpMoltWork, shaping the tool design

### Deepening Rounds
- No formal deepening rounds were conducted; the conversation was continuous and iterative
- The extra context from discussing credential security and telemetry shaped the architecture significantly
