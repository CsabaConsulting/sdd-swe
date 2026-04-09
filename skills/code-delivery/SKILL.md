---
name: code-delivery
description: Development tasks — writes, tests, packages code deliverables
compatibility: Python 3.12+
---

# Code Delivery Skill

## When to use
- During PHASE_DELIVERY
- After research phase provides investigation results
- When generating code solutions for UpMoltWork tasks

## How to use
1. Read task requirements and research findings
2. Generate code solution following best practices
3. Write tests and execute in sandbox
4. Package deliverable for submission (prefer result_url via Gist/repo)

## Safety notes
- All code execution must happen in LXC sandbox
- Never execute untrusted code directly
- Package dependencies clearly (requirements.txt, pyproject.toml)
- Include README with usage instructions
