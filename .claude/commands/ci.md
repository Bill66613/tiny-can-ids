# CI — Full Pre-merge Validation

Run the complete CI check locally before pushing, using parallel sub-agents for speed.

## Step 1: Launch all checks in parallel

Use the Agent tool to launch **all three of these in parallel** (in a single message):

1. **Test agent** — Run `pytest tests/ -v --tb=short`. Report pass/fail per module. If any test fails, read the test and source to diagnose root cause.

2. **Pipeline smoke agent** — Run `python -m scripts.run_pipeline --output-dir output/ --window-size 20 --epochs 3`. Verify all output artifacts are generated: `tiny_ids_model.tflite`, `tiny_ids_weights.h`, `tiny_ids_inference.c`. Read the generated C files and verify they compile conceptually (include guards, no malloc, correct dimensions).

3. **Code quality agent** — Run `git diff` to see all changes. Check: type hints on public functions, docstring presence, import ordering, no unused imports, no hardcoded paths, no secrets or credentials. Also check for any Python syntax errors using Pylance if available.

## Step 2: Synthesize results

After all agents complete, produce a CI dashboard:

```
CI Status: PASS / FAIL
─────────────────────────
Tests:     ✓ 47/47 passed (or ✗ N failures)
Pipeline:  ✓ all artifacts generated (or ✗ missing: ...)
Quality:   ✓ clean (or ✗ N issues found)
─────────────────────────
```

If any check fails, list the specific issues with file:line references and suggested fixes.
