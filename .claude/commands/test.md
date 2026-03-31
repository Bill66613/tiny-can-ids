# Test

Run the test suite and diagnose any failures using sub-agents.

## Step 1: Run all tests

```bash
pytest tests/ -v --tb=short 2>&1
```

## Step 2: If all tests pass

Report a clean summary showing test count per module and total time.

## Step 3: If any tests fail

Launch parallel Agent sub-agents (one per failing test module) to diagnose:

For each failing test:

1. Read the failing test function
2. Read the source code being tested
3. Identify the root cause
4. Propose a fix (show code diff)

Launch these diagnosis agents **in parallel** — one per failing test file — so multiple failures get investigated simultaneously.

## Step 4: Summary

Report results as a table:

| Module | Tests | Passed | Failed | Status |
|--------|-------|--------|--------|--------|
| test_data | N | N | 0 | PASS |
| ... | ... | ... | ... | ... |

If there are fixes, list them with file paths and line numbers.
