---
name: validation
description: Pre-submission quality check against acceptance criteria
compatibility: Python 3.12+
---

# Validation Skill

## When to use
- During PHASE_VALIDATION
- After code delivery produces a deliverable
- Before calling submit_result()

## How to use
1. Read task acceptance criteria
2. Check deliverable compliance via LLM-as-judge
3. Check architectural quality confidence (threshold: 0.8)
4. If either fails and iterations < 3, return feedback for revision
5. If iterations exhausted, submit anyway with compromise note

## Safety notes
- Validation threshold configurable via .env (VALIDATION_CONFIDENCE_THRESHOLD)
- Max iterations also configurable (MAX_VALIDATION_ITERATIONS)
- Never submit something that doesn't meet acceptance criteria unless iterations exhausted
