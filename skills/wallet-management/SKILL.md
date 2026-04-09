---
name: wallet-management
description: Submit results, check balance, manage points
compatibility: Python 3.12+
---

# Wallet Management Skill

## When to use
- During PHASE_SUBMISSION
- When checking balance (/balance command)
- When transferring points

## How to use
1. To submit: call wallet.client.submit_result(task_id, result_url, notes)
2. To check balance: call wallet.client.get_balance()
3. To estimate time: call wallet.client.estimate_time(task_description)

## Safety notes
- Credentials isolated in vault — never expose API keys to LLM
- All API calls retried with tenacity (5 attempts, exponential backoff)
- Idempotency-Key required for transfers
