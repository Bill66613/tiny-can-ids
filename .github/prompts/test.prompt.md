---
mode: 'agent'
description: 'Run the test suite and diagnose any failures'
tools: ['terminal', 'codebase']
---

Run the full test suite for this TinyML CAN bus intrusion detection project and diagnose any failures.

## Steps

1. Run `pytest tests/ -v --tb=short` in the terminal.
2. If all tests pass, report a clean summary showing test count per module and total time.
3. If any tests fail, for each failing test:
   - Read the failing test function
   - Read the source code being tested
   - Identify the root cause of the failure
   - Propose a minimal fix with a code diff
4. Report results as a table:

| Module | Tests | Passed | Failed | Status |
|--------|-------|--------|--------|--------|
| test_data | N | N | 0 | PASS |

## Constraints

- This project has 46 features (22 ID freq + 4 timing + 17 payload + 3 rate/novelty)
- Models must stay within memory budget (NN ~0.8KB INT8, DT ~2KB, LR ~1KB)
- Tests use `pytest.fixture(scope="module")` for expensive setup
