# Diagnose

Investigate and diagnose an issue in the codebase: $ARGUMENTS

## Step 1: Parallel investigation

Launch these agents **in parallel**:

1. **Error reproduction agent** — If the user describes an error, attempt to reproduce it. Run the failing command or test. Capture the full traceback and error context.

2. **Codebase search agent** — Search for all code related to the reported issue using Grep and Glob. Find the relevant functions, their callers, and their tests. Map the call chain from entry point to the error location.

3. **Recent changes agent** — Run `git log --oneline -20` and `git diff` to check if recent changes may have introduced the issue. Look for modifications to the files involved in the error.

## Step 2: Root cause analysis

Based on agent findings:

1. Identify the exact line(s) causing the issue
2. Explain **why** it fails (not just what fails)
3. Check if this is a regression (worked before a recent change) or a latent bug

## Step 3: Propose fix

- Show a minimal code diff that fixes the issue
- Explain why the fix is correct
- Identify any related code that might have the same bug pattern
- Suggest a test case that would catch this bug in the future

## Step 4: Validate

Run `pytest tests/ -v` to confirm the fix doesn't break anything else.
