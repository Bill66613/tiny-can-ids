---
mode: 'agent'
description: 'Root-cause investigation of a bug or issue'
tools: ['terminal', 'codebase']
---

Investigate and diagnose the following issue: {{input}}

## Investigation Steps

1. **Reproduce** — If an error is described, attempt to reproduce it by running the failing command or test. Capture the full traceback.

2. **Search** — Find all code related to the issue using codebase search. Map the call chain from entry point to the error location. Check callers and tests.

3. **Recent changes** — Run `git log --oneline -20` and `git diff` to check if recent changes may have introduced the issue.

## Root Cause Analysis

- Identify the exact line(s) causing the issue
- Explain **why** it fails (not just what fails)
- Determine if this is a regression or a latent bug

## Proposed Fix

- Show a minimal code diff that fixes the issue
- Explain why the fix is correct
- Identify related code with the same bug pattern
- Suggest a test case that would catch this bug

## Validation

Run `pytest tests/ -v` to confirm the fix doesn't break anything else.
