---
mode: 'agent'
description: 'Run full local CI checks before pushing'
tools: ['terminal', 'codebase']
---

Run the complete local CI validation for this TinyML CAN bus IDS project.

## Checks to Run

### 1. Tests
Run `pytest tests/ -v --tb=short`. Report pass/fail per module. If any test fails, read the test and source to diagnose.

### 2. Pipeline Smoke Test
Run `python -m scripts.run_pipeline --output-dir output/ --window-size 20 --epochs 3`. Verify all output artifacts are generated. Read the generated C files and verify they have no syntax issues (include guards, no malloc, correct dimensions).

### 3. Code Quality
Run `git diff` to see all changes. Check:
- Type hints on public functions
- Docstring presence
- Import ordering (stdlib → third-party → local)
- No unused imports
- No hardcoded paths
- No secrets or credentials

## Report

Produce a CI dashboard:

```
CI Status: PASS / FAIL
─────────────────────────
Tests:     ✓ N/N passed (or ✗ N failures)
Pipeline:  ✓ all artifacts generated (or ✗ missing: ...)
Quality:   ✓ clean (or ✗ N issues found)
─────────────────────────
```

If any check fails, list specific issues with file:line references and suggested fixes.
