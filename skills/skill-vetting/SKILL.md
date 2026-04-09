---
name: skill-vetting
description: Security skill — examines 3rd party SKILL.md files for malicious intent
compatibility: Python 3.12+
---

# Skill Vetting Skill

## When to use
- During PHASE_DISCOVERY (when new skill downloaded from catalog)
- Before activating any 3rd party skill
- Gate 2 of 3-gate verification (after checksum, before sandbox)

## How to use
1. Read downloaded SKILL.md content
2. Check for suspicious patterns:
   - Credential patterns (API keys, passwords)
   - Command injection (os.system, subprocess, eval, exec)
   - Network exfiltration (requests to unknown hosts)
   - File system writes outside expected paths
3. Check source reputation (official catalog > community > unknown)
4. Return vetting result: pass or reject with reason

## Safety notes
- This skill is CRITICAL for security — never disable 3-gate verification
- First-time skills ALWAYS require human approval before activation
- Even if vetting passes, sandbox test (Gate 3) must also pass
