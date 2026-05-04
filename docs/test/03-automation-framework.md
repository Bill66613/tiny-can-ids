# Test Automation Framework

## Overview

The **Test Automation Framework** defines how, when, and which tests run, with clear categorization and CI/CD integration strategy.

---

## Test Categorization Hierarchy

See [diagrams/04-test-categories.puml](diagrams/04-test-categories.puml) for the test organization showing:
- 84 unit tests (data, features, models, export)
- 8 integration tests (pipeline output validation)
- 5 performance tests (baseline, memory profiling)

---

## CI/CD Test Matrix

### Fast Suite (5 minutes) — Runs on every commit

```yaml
# GitHub Actions trigger: push, pull_request

jobs:
  fast-tests:
    runs-on: ubuntu-latest
    steps:
      - Run unit tests (test_data, test_features, test_models, test_export)
      - Run integration tests on tiny/small scenarios (outputs validation)
    timeout: 10 minutes
    if: all tests pass, proceed to full suite
```

**Tests Included:**
- All unit tests (12 + 15 + 28 + 29 = 84 tests)
- Integration tests: pipeline_runs_tiny, c_headers_valid, c_source_valid (~3 tests)
- Total: ~87 tests in ~5 minutes

---

### Full Suite (15 minutes) — Runs on PR merge

```yaml
# Trigger: pull_request, manual trigger

jobs:
  full-tests:
    runs-on: ubuntu-latest
    steps:
      - Run fast suite (5 min)
      - Run integration tests on medium scenario (full output validation)
      - Run performance baseline comparison
      - Generate test report
    timeout: 20 minutes
```

**Tests Included:**
- Fast suite (~87 tests)
- Integration tests: all 8 validation tests on medium dataset (~8 tests)
- Performance tests (~5 tests)
- Total: ~100 tests in ~15 minutes

---

## Test Markers & Categorization

```python
# conftest.py or pytest.ini

[tool.pytest.ini_options]
markers = [
    "unit: Unit tests (isolated functions)",
    "integration: Integration tests (full pipeline execution)",
    "integration_tiny: Integration test on tiny scenario (~1 sec)",
    "integration_small: Integration test on small scenario (~5 sec)",
    "integration_medium: Integration test on medium scenario (~15 sec)",
    "integration_large: Integration test on large scenario (~45 sec)",
    "performance: Performance/regression tests",
    "slow: Slow tests (> 10 sec)",
    "real_data: Requires real dataset",
    "multiclass: Multi-class tests",
]
```

---

## Test Execution Commands

### Fast Smoke Test (Local, 30 sec)

```bash
# Run only unit tests for quick feedback
pytest tests/unit/ -v

# Expected: ~30 sec, 84 tests pass
```

### Fast Suite (Local + CI, 5 min)

```bash
# Unit + tiny integration tests
pytest tests/unit/ tests/integration/ -m "integration_tiny" -v --tb=short

# Expected: ~5 min, 87 tests pass
```

### Full Suite (CI, 15 min)

```bash
# All tests except slow
pytest tests/ -m "not slow" -v

# Expected: ~15 min, 100 tests pass
```

### Test Single Integration Scenario (Local)

```bash
# Test only tiny scenario (quick validation)
pytest tests/integration/ -m "integration_tiny" -v -s

# Test only medium scenario (full validation)
pytest tests/integration/ -m "integration_medium" -v -s

# Test only large scenario (stress test)
pytest tests/integration/ -m "integration_large" -v -s
```

---

## GitHub Actions Workflow

```yaml
# .github/workflows/testing.yml

name: Testing Pipeline

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

env:
  PYTHON_VERSION: "3.11"
  CACHE_VERSION: "v1"

jobs:
  # ============================================================
  # JOB 1: Fast unit + tiny integration tests (5 min)
  # ============================================================
  fast-tests:
    name: "Fast Tests (Unit + Integration Tiny)"
    runs-on: ubuntu-latest
    timeout-minutes: 10
    
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
          cache: 'pip'
      
      - name: Install dependencies
        run: pip install -e ".[dev]"
      
      - name: Run unit tests
        run: pytest tests/unit/ -v --tb=short
      
      - name: Run integration tests (tiny scenarios)
        run: pytest tests/integration/ -m "integration_tiny" -v --tb=short
      
      - name: Upload test results
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: fast-test-results
          path: .pytest_cache/

  # ============================================================
  # JOB 2: Full tests with medium and large scenarios (15 min)
  # ============================================================
  full-tests:
    name: "Full Tests (Integration All Scenarios)"
    needs: fast-tests
    if: success()
    runs-on: ubuntu-latest
    timeout-minutes: 20
    
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
          cache: 'pip'
      
      - name: Install dependencies
        run: pip install -e ".[dev]"
      
      - name: Run integration tests (medium & large scenarios)
        run: pytest tests/integration/ -m "integration_medium or integration_large" -v --tb=short
      
      - name: Run performance baseline
        run: pytest tests/performance/ -v --tb=short
      
      - name: Generate test report
        if: always()
        run: |
          pytest tests/ --html=report.html --self-contained-html
      
      - name: Upload test report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: full-test-report
          path: report.html
          retention-days: 30

  # ============================================================
  # JOB 3: Pipeline smoke test
  # ============================================================
  pipeline-smoke:
    name: "Pipeline Smoke Test"
    needs: fast-tests
    if: success()
    runs-on: ubuntu-latest
    timeout-minutes: 60
    
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
          cache: 'pip'
      
      - name: Install dependencies
        run: pip install -e ".[dev]"
      
      - name: Run full pipeline (synthetic data)
        run: python -m scripts.run_pipeline --output-dir build/pipeline --window-size 50 --epochs 10
      
      - name: Verify output artifacts
        run: |
          test -f build/pipeline/tiny_ids_tnn_weights.h
          test -f build/pipeline/tiny_ids_tnn.c
          test -f build/pipeline/tiny_ids_lr_weights.h
          test -f build/pipeline/tiny_ids_lr.c
          echo "All pipeline artifacts verified!"
      
      - name: Upload pipeline artifacts
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: pipeline-output
          path: build/pipeline/
          retention-days: 7

```

---

## Test Results Dashboard (Concept)

```
┌─────────────────────────────────────────────────────────────┐
│                    TEST RESULTS DASHBOARD                   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Last Run: 2026-04-09 14:32:00 UTC                          │
│  Status: ALL PASSED                                         │
│                                                             │
│  ┌──────────────────────┬────────┬────────────┬────────┐    │
│  │ Test Suite           │ Count  │ Time       │ Status │    │
│  ├──────────────────────┼────────┼────────────┼────────┤    │
│  │ Unit Tests           │   84   │  0m 45s    │ PASS   │    │
│  │ Integration Tiny     │    3   │  0m 45s    │ PASS   │    │
│  │ Integration Small    │    5   │  1m 30s    │ PASS   │    │
│  │ Integration Medium   │    5   │  3m 45s    │ PASS   │    │
│  │ Integration Large    │    1   │  1m 20s    │ PASS   │    │
│  │ Performance Tests    │    5   │  2m 30s    │ PASS   │    │
│  ├──────────────────────┼────────┼────────────┼────────┤    │
│  │ TOTAL                │  102   │  9m 50s    │ PASS   │    │
│  └──────────────────────┴────────┴────────────┴────────┘    │
│                                                             │
│  Coverage: 94.2% (updated this run)                         │
│  Trend: up 0.5% from previous 2 weeks                       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Performance Baseline & Regression Detection

### Data-Driven Threshold Strategy

Instead of fixed thresholds, performance baselines are **statistically derived** from historical test runs:

1. **Capture baseline**: Run test suite 10 times in CI environment, record execution times
2. **Calculate statistics**: Compute mean (μ) and standard deviation (σ)
3. **Dynamic threshold**: Threshold = μ + 2σ
   - Adapts automatically to CI environment noise
   - Distinguishes real slowdowns from variance
   - Reduces false positives and false negatives

**Example:**
- Unit tests run 10 times: [45.2, 46.1, 45.8, 46.3, 45.5, 46.0, 45.7, 46.2, 45.9, 46.1]
- Mean (μ) = 45.88 seconds
- Stddev (σ) = 0.35 seconds
- Threshold = 45.88 + (2 × 0.35) = **46.59 seconds**

### Regression Detection

When tests run:
- If current time < 46.59s: PASS (normal variance)
- If current time > 46.59s: FAIL (genuine regression detected)

The failure message includes context: actual time, threshold, mean, and stddev for debugging.

### Baseline Recalibration Options
- Python version upgrade, CI runner change
- Major test infrastructure refactoring
- Time-based recalibration every day as safety net
- Alerts if false positive rate increases (>10% of runs)
- Trigger: Manual GitHub Actions workflow dispatch

---

## Failure Handling Strategy

### Test Failure Response

See [diagrams/05-failure-response.puml](diagrams/05-failure-response.puml) for the decision logic:
- **Unit test failure** → Stop fast suite, don't run integration tests
- **Integration failure** → Mark scenario as failed, optionally run other scenarios for visibility
- **Report generation** → All failures are logged and reported
- **Team notification** → Email sent to team only for pull request failures

---

See [01-data-feeder-design.md](01-data-feeder-design.md), [02-integration-pipeline-design.md](02-integration-pipeline-design.md), and [README.md](README.md) for detailed specifications.
