# About Project

## Inspiration
Current autonomous freelance agents often operate as unpredictable black boxes. Furthermore, most agent frameworks ignore fundamental security principles—they eagerly grant LLMs access to sensitive API credentials or execute unreliable code payloads locally without isolation. We were inspired to build Aegis to solve this dual problem: we wanted an agent that combines highly dynamic adaptability with rock-solid, non-negotiable security boundaries. 

## What it does
Aegis autonomously scans the UpMoltWork marketplace, evaluates available tasks using customized heuristics, bids on assignments, and executes deliverables. Critically, if Aegis encounters a task that requires capabilities beyond its built-in knowledge base, it dynamically searches online catalogs for new skills. It downloads the required `SKILL.md` specifications and Python modules and then passes them through a strict 3-gate vetting process:
1. Checksum verification
2. Heuristic screening (using Llama Prompt Guard & Llama Guard 3)
3. Simulated execution in an isolated Podman/LXC sandbox

Only after clearing these gates—and receiving manual operator approval through asynchronous IMAP email polling—does Aegis load the skill into its Orchestrator Engine to complete the task.

## How we built it
Aegis is built in Python 3.12+ and centers around a finite state machine Orchestrator (Discovery, Research, Delivery, Validation, Submission). 
- We utilized **Textual** to create a robust 4-region Terminal UI.
- State is managed durably using **SQLite (aiosqlite)**.
- We used **Podman / LXC** to execute untrusted code in lightweight, network-disabled containers.
- We implemented **Meta Prompt Guard and Llama Guard 3** as direct imports to thoroughly screen all inbound and outbound LLM traffic.
- **OpenTelemetry and Phoenix** were integrated for deep, local observability into every LLM request and phase transition.
- The **UpMoltWork API** and **OpenRouter API** power the bidding cycles and LLM evaluations.

## Challenges we ran into
Integrating robust security pipelines directly into the agent’s core lifecycle was incredibly demanding. Running heavy local guardrail models would occasionally cause OOM errors or block startup. We overcame this by refactoring our guardrail service to use async singleton loaders and graceful pass-through degradation, preventing the agent from crashing under extreme resource load. Additionally, building a reliable IMAP email polling mechanism—designed to be completely idempotent and resilient against replay attacks without relying on external webhooks—required rigorous state management.

## Accomplishments that we're proud of
Instead of building a rigid Swarm of specialized sub-agents, we implemented a **Progressive Disclosure** pattern. Aegis's ability to extend its own skills dynamically from online catalogs (after vetting) is a massive leap over static multi-agent architectures. We’re also incredibly proud of the Validation Loop: an automated "LLM-as-judge" mechanism where Aegis self-polices its own deliverable against the task's stated acceptance criteria and architectural best practices, iterating autonomously up to 3 times to improve quality before final submission.

## What we learned
We discovered that stripping down a project to a single orchestrator that dynamically loads behavior based on the current state phase massively reduces LLM context bloat and operational complexity. We also realized earlier than usual that solidifying our test infrastructure (`pytest` alongside mocked databases and external APIs) was vital. Dedicating time to our test suite mid-hackathon stabilized the complex phase transitions and enabled us to confidently refine the async state machine.

## What's next for Aegis: Guarded Skill-Discovering Freelance Agent
We plan to introduce a custom ML model overlay to analyze Aegis's historical bidding data, allowing it to optimize its `price_points` and win rate autonomously over time. More ambitiously, we want to evolve Aegis from simply *discovering and downloading* new skills from catalogs to securely *generating its own custom SKILL.md specifications from scratch* when confronted with entirely novel task parameters.
