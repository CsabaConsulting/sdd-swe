# Hackathon Submission: Aegis - Autonomous Freelance Agent

## Core Story
Autonomous freelance agents on platforms like UpMoltWork often face three critical failures:
1. **Opaque Operations:** They operate as black boxes—users cannot see what the agent is doing or why it made certain decisions.
2. **Missing Guardrails:** They execute without safety constraints—credentials leak to LLMs, prompt injections go undetected, and malicious code runs unsandboxed.
3. **Fixed Capabilities:** They have baked-in, static skills, making them unable to adapt to new task types without manual redeployments.

**Aegis** solves this. It is a guarded, skill-discovering autonomous agent. It monitors the UpMoltWork marketplace for tasks, evaluates and bids intelligently, executes deliverables under strict security guardrails, and—most importantly—extends its own capabilities dynamically by discovering and downloading new skills from online catalogs.

## What We Built

We built a single-process Python application centered around an **Orchestrator Engine**. This engine runs a finite state machine managing task lifecycles across five phases: Discovery, Research, Delivery, Validation, and Submission.

Instead of a complex Swarm or multi-agent P2P system, Aegis uses a **Progressive Disclosure** pattern. It dynamically loads only the skills (SKILL.md specs + Python modules) needed for the current phase.

**The "Wow" Moment:**
Aegis's defining feature is its **Dynamic Skill Discovery and 3-Gate Trust Model**. When Aegis encounters a task it doesn't have the built-in skill for, it queries online catalogs to find a match. Before activating any third-party skill, Aegis runs a strict 3-gate security check:
1. **Checksum verification** against catalog hashes.
2. **Heuristic scanning** (using Prompt Guard and Llama Guard 3) to look for credential scraping or command injection.
3. **Sandboxed execution** testing the skill in an isolated, network-disabled Podman container.

Only after passing these gates—and receiving manual approval via an asynchronous IMAP email polling system—is the skill cached and activated.

## Why We Chose It

**Architecture Evolution**
Our initial design was a multi-agent P2P system with five separate processes talking over HTTP. However, we quickly pivoted to an **Agent Skills** specification model (inspired by agentskills.io). We realized that dynamic capability loading (via markdown and scripts) supervised by a central Orchestrator is vastly simpler to reason about, significantly reduces context bloat, and decreases operational complexity.

**Focus on Security Over Convenience**
We deliberately chose to implement robust security borders. We treated the Wallet service as a direct module with strict credential isolation (credentials never enter the LLM context). We integrated Meta's Llama Prompt Guard and Llama Guard 3 to monitor all inbound and outbound LLM traffic.

**Lightweight Execution**
We chose to execute code deliverables inside lightweight rootless **Podman** containers rather than full Docker setups to keep execution highly secure (filesystem read-only, network disabled) but computationally cheap.

## What We Learned Along the Way

1. **Security Pipelines Require Graceful Degradation:** Implementing the guardrails was complex. We learned that loading heavy local models can block startup or cause OOM errors. We refactored the guardrail service to use async singleton loaders and degraded pass-through modes to prevent the agent from crashing when under high resource contention.
2. **LLMs as Evaluators are Powerful:** We successfully implemented an "LLM-as-judge" for the Validation Loop. It tests both acceptance criteria compliance and architectural quality confidence before submitting work, highlighting how LLMs can effectively self-police iterative delivery loops.
3. **Asynchronous Human-in-the-Loop:** We initially planned a complex web admin dashboard, but realized that a simple, robust IMAP email polling mechanism was much more effective. Aegis can email the operator for approval when it discovers a new skill, and the operator can simply reply `/approve <skill-name>`, allowing the agent to continue working without being strictly blocked.
4. **The Importance of Test Infrastructure:** Even in a fast-paced hackathon, we learned that writing automated tests for the state machine and mocking the UpMoltWork API was the only way to quickly refactor complex phase transitions. Dedicating an entire iteration purely to test suite setup (using `pytest` and `aiosqlite` mock DBs) paid massive dividends when polishing the final agent logic.
