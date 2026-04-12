# Reflection — Aegis: Spec-Driven Development Experience

**Date:** 2026-04-12
**Project:** Aegis — Autonomous Freelance Agent System for UpMoltWork
**Methodology:** Spec-Driven Development (SDD) via hackathon-in-a-plugin curriculum

---

## Goals (from Learner Profile)

This was an **evaluation run**, not a beginner learning exercise. My specific goals:

- Assess what product maturity level SDD can achieve
- Compare resulting architecture to best practices
- Evaluate documentation thoroughness
- Measure test coverage
- Understand how SDD compares to prior structured planning approaches I've tried

**Context:** Veteran software engineer (~30 years), strong full-stack background, currently working in generative AI/ML. Not a first-timer to structured planning concepts.

---

## Conversational Quiz — Key Insights

### 1. Context is Everything

The planning documents (learner profile, scope, PRD, spec, checklist) had a **positive effect on quality**. The scoping and PRD steps were meticulous — they took more time than I expected, but that time was beneficial because the end result is more well-rounded.

The process pushes back and makes you accountable for important decisions. I appreciate when an AI agent reverses the conversation and starts questioning me. If that doesn't happen, I become skeptical. I had to leave sessions open overnight multiple times, but the end result is more thorough — fewer guessed aspects, less AI slop. **The longer this process is, the better.**

### 2. Why Flipped Interaction Works

The questions progressively got more detailed as the process went on. Higher-level and mid-level decisions were settled first, then implementation details emerged. This was planned intentionally — the user can approach the whole process layer by layer. A one-line prompt would result in many more guesses from the coding agent, and these things need to be argued about, not assumed.

### 3. Fighting Structural Problems

Each SDD phase resulted in one or more result documents which fed as input into later processes. This minimizes amnesia or forgetfulness. The process also encouraged performing a clear operation before each phase. While Claude Code auto-compacts context sometimes, explicit clearing is better. I also enabled the Zilliz memsearch plugin to augment retrieval — the documents remain the deterministic chain.

### 4. What I'd Do Differently

I amended the scope phase multiple times. If I had all my thoughts together the first time, it would look cleaner — but it didn't hurt to amend. Sometimes the pushback resulted in **13 questions to answer, each with at least 3-4 sub-questions**. That's way too much — I wrote whole essays. I don't think I could have done much against that, but it's good to plan that certain steps would truly take hours. I had to leave sessions open overnight to continue answering the next night.

**Key realization:** That 13-question deepening round was a signal — my scope was wide enough that the agent needed to constrain 13 different dimensions. Next time, I'd be even more specific upfront to reduce the probing axes.

---

## Project Review — Strengths & Growth Areas

### 1. Scope & Idea Clarity

**Strength:** The scope doc nails a specific problem with teeth: autonomous agents on UpMoltWork "operate as opaque black boxes" with "credentials leaked to LLMs." The user is clearly defined: "a solo operator or small team who wants to deploy an autonomous agent." The cuts are real: no web UI, no multi-platform support, no custom skill generation. The 6-page scope doc is detailed enough to build from.

**Growth Area:** The scope tries to do too much for a 3-4 hour hackathon. Building: dynamic skill discovery with 3-gate verification, LXC/Podman sandboxing, two guardrail ML models, wallet credential isolation, Phoenix tracing, email alerts, *and* a terminal UI is enormous. Future iteration: cut 2-3 "built-in skills" to focus on proving the skill *discovery* mechanism itself (the real differentiator).

### 2. Requirements Thinking

**Strength:** 15 user stories across 5 epics, each with 4-7 testable acceptance criteria. Edge cases surfaced explicitly: "When zero tasks available, terminal shows 'Waiting for tasks...'", "If guardrail service is down, agent halts all tasks." The PRD is substantially more detailed than the scope doc.

**Growth Area:** Some ambiguity remains that causes friction during build. For example, what happens when time/cost limit is reached *during* validation iteration — submit partial or abandon? I resolved this in `/spec` as "submits with architecture incomplete flag," but the PRD should've been explicit. Also, "agent learns from past bids" implies persistent state not in the initial schema. These gaps show why PRD→spec deepening rounds matter.

### 3. Technical Decisions

**Strength:** Intentional stack choices with clear rationale: `textual` over `rich`, `tenacity` over `stamina`, direct imports vs. HTTP services, Podman over LXC. The SQLite schema has 4 tables with proper indexes and idempotency enforcement. The 2,909-line codebase matches the spec's architecture. Phase transition map is clean.

**Growth Area:** Tension between "direct imports" and "credential isolation." Reading from `os.environ` is better than hardcoding, but there's no enforcement that the LLM *can't* access `vault.py`. A stronger isolation would be a process boundary with IPC, not just module-level separation. Similarly, guardrails run in the same process — no enforcement that *all* LLM calls pass through them. The spec could be sharper about *how* these invariants are maintained.

### 4. Plan vs. Reality

**Strength:** Clear mapping from spec to code: `src/orchestrator/engine.py` (state machine), `src/guardrails/service.py` (Prompt Guard + Llama Guard 3), `src/skills/validation.py` (LLM-as-judge), `src/execution/sandbox.py` (Podman with subprocess fallback). All 12 `/build` items present. 10-test suite (150 tests) written and passing. `process-notes.md` accurately reflects pivots.

**Growth Area:** The PRD lists 9 core features, but many are stubs or partial. Guardrail service has model loading but confirmation of `check_input()`/`check_output()` is incomplete without running. Email alerts exist but aren't clearly wired into Orchestrator's error handling. Skill discovery pipeline exists but evidence of calling 4 configured catalogs is missing. The *architecture* is solid, but the *integration* is incomplete. This isn't unusual for a hackathon, but worth naming.

### 5. How I Worked

**Strength:** 263-line `process-notes.md` documenting every pivot and decision. Made real calls: "Wallet as service, not agent," "LXC → Podman," "Direct imports for guardrails." Didn't just accept suggestions — redirected when necessary. The codebase and test suite show I did the work myself. Completed all 12 `/build` items and all 10 `/iterate` test items.

**Growth Area:** Looking at deepening round notes, I accepted the proposed architecture without much pushback on *complexity*. 12 items for one `/build` pass is a lot. I could have said "let's cut skill discovery and focus on proving out core Orchestrator + 2 skills + guardrails end-to-end first." Accepting all 12 items without negotiation suggests I over-ambitiously scoped myself. Future iteration: push back harder on what's *essential* for the demo, not what's *possible* for the build.

---

## Overall Assessment

### What Went Well

1. **Documentation thoroughness:** 5 docs (~40 pages) + 263-line process notes. The specs are detailed enough to build from, and the PRD has testable criteria.

2. **Architecture quality:** Clear separation of concerns, explicit interfaces, retry logic (`tenacity`), credential isolation (env vars), guardrail filtering, sandboxed execution. The phase transition map and SQLite schema are well-designed.

3. **Test coverage:** 150 tests across 11 modules covering bidding, config, guardrails, integration lifecycle, orchestrator, sandbox, store, and validation. Tests mock LLMs, sandbox execution, and API calls.

4. **Process fidelity:** The SDD process kept its bearings despite essay-size Q&A sessions. Claude Code's context management (auto-compaction + explicit documents) meant the agent stayed focused across overnight breaks.

5. **Learning about scope breadth:** The 13-question deepening rounds with 4-5 sub-questions each taught me my scope was too wide. That's valuable meta-learning about how to scope future projects.

### What I'd Improve

1. **Scope focus:** For a 3-4 hour hackathon, 10+ complex subsystems (skill discovery, 5 built-in skills, guardrails, sandbox, wallet isolation, email alerts, terminal UI, Phoenix tracing) is too much. Next time, I'd cut to the core differentiator (skill discovery with 3-gate verification) and build just that + Orchestrator + 1-2 skills.

2. **Spec reconciliation:** The spec is static — it doesn't update when architectural drift happens during iterations (LXC→Podman, direct imports, etc.). A future enhancement: `/iterate` should include a "spec reconciliation" step to keep the spec a living document.

3. **Code quality gates:** The codebase needs Ruff linting and pre-commit hooks. I could have specified this during `/spec` — future iteration would add it. Tradeoff: enforcing linters may slow down the process, but it's worth it for production readiness.

4. **Integration completeness:** The architecture is sound, but not all features are fully wired together. The guardrail service, email alerts, and skill discovery pipeline have partial implementations. A full end-to-end test confirming all pieces connect would've been the final proof.

5. **Negotiating complexity:** I accepted the 12-item `/build` checklist without pushback. I should have questioned whether all 12 are essential for the demo and cut 2-3 to ensure the core flow was polished.

---

## Surprises

1. **Depth of the deepening rounds:** I was surprised to face 13 main questions with 4-5 sub-questions each during `/scope` and `/prd`. That highlighted **how wide my initial scope really was**. Fortunately, LLMs have large enough context that the process stayed on track despite essay-length answers.

2. **How much coding agents change software:** It's surprising how much coding agents have changed software development compared to what we had only 3 years ago before ChatGPT. Getting from idea to 2,909 lines of structured Python with a test suite used to take weeks of solo work or a small team. Now the bottleneck is "how clearly can you articulate intent," not "how fast can you type." That's a fundamentally different constraint surface.

3. **The value of friction:** The extra time spent in scoping and PRD felt slow at first, but it compounds. Decisions made upfront prevented rework later. The process felt like "design debt repayment" upfront instead of mid-build.

4. **AI reversing the conversation:** When the agent started questioning me, I became more confident in the output. That reversal is a quality signal — it means the agent is stress-testing my thinking, not just performing compliance.

---

## Would I Use SDD Again?

**Yes.** Overall I'm satisfied with the SDD methodology compared to other structured planning approaches I've tried. It didn't spec out the implementation function-by-function, but I think that's an **advantage** — it gives the agent flexibility to adapt while maintaining architectural coherence.

For a production project (not a hackathon), I'd add:
- Ruff linting + pre-commit hooks
- CI/CD with test coverage gates
- More thorough integration tests (real UpMoltWork API, real LLM calls with rate limiting)
- Spec reconciliation during `/iterate` to keep docs in sync with code
- Stricter scope negotiation — cutting to the core differentiator and building it well vs. building many features partially

**Bottom line:** SDD produces better architecture and documentation than ad-hoc planning, but it requires discipline to stay focused on what fits in the time window. The process works. The trick is scoping to the methodology, not the other way around.
