# Implement

Add a new feature or capability to the tiny-can-ids pipeline: $ARGUMENTS

## Step 1: Research phase (parallel agents)

Launch these agents **in parallel** to gather context:

1. **Codebase exploration agent** — Search the codebase for all files, functions, and patterns related to the requested feature. Identify which modules need changes and what existing code can be reused.

2. **Constraint check agent** — Analyze how the requested feature impacts TinyML constraints: memory budget (NN ~0.8KB INT8, DT ~2KB, LR ~1KB), the fixed 43-feature vector, generated C code compatibility, INT8 quantization range. Flag any constraint violations early.

3. **Test survey agent** — Review existing tests in `tests/` to understand testing patterns, fixtures, and helper functions. Identify which test file(s) should receive new tests for this feature.

## Step 2: Plan

Based on agent findings, create an implementation plan:

- Files to modify (with specific functions)
- New files to create (if absolutely necessary)
- Test cases to add
- Any constraint mitigations needed

Present the plan to the user for confirmation before proceeding.

## Step 3: Implement

Follow existing conventions:

- Type hints on all public function signatures
- NumPy-style docstrings on all public functions
- Import ordering: stdlib → third-party → local
- Module-scoped fixtures for expensive test setup

## Step 4: Validate

Run `pytest tests/ -v` and verify all tests pass. If the feature changes the model or features, also run:

```bash
python -m scripts.run_pipeline --output-dir output/ --window-size 20 --epochs 3
```
