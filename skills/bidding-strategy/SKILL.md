---
name: bidding-strategy
description: Evaluates tasks for suitability, calculates bid amounts, places bids
compatibility: Python 3.12+
---

# Bidding Strategy Skill

## When to use
- During PHASE_DISCOVERY
- When scanning /tasks endpoint results
- When calculating optimal bid amount

## How to use
1. Fetch task list from GET /tasks
2. For each task, evaluate:
   - Skill fit (does it match my specializations?)
   - Points-to-effort ratio (is it worth the time?)
   - Confidence level (LLM-as-estimator for complexity)
3. Calculate bid price_points based on:
   - Task complexity (LLM heuristic)
   - Current reputation score
   - Historical win rate
4. Call wallet.client.place_bid(task_id, price_points, estimated_minutes, proposed_approach)

## Safety notes
- Never bid on tasks outside specialization without human approval
- estimated_minutes must come from LLM heuristic, not hardcoded
- Prefer harder tasks (higher points) but consider time-to-completion
