# Testing Framework for tiny-can-ids

This directory contains comprehensive integration testing infrastructure for the end-to-end CAN bus intrusion detection pipeline.

## Overview

The testing framework validates that `scripts/run_pipeline.py` executes correctly across different data scenarios and produces valid C deployment artifacts.

### Three Core Components

**1. Data Feeder System** ([01-data-feeder-design.md](01-data-feeder-design.md))
- Centralized test data provisioning
- Predefined scenarios: tiny (100/20), small (500/100), medium (1500/300), large (5000/1000)
- Reproducible via fixed seeds
- Extensible for custom test scenarios

**2. Integration Test Suite** ([02-integration-pipeline-design.md](02-integration-pipeline-design.md))
- Validates full pipeline execution
- 8 tests covering: pipeline execution, C header validation, C source validation, C compilation, model sizes, TFLite export, metrics generation, and large dataset handling
- Tests across all scenario sizes for comprehensive coverage
- Validates output artifacts (C `.h` and `.c` files, `.tflite`, metrics)

**3. CI/CD Automation** ([03-automation-framework.md](03-automation-framework.md))
- Fast suite (5 min): Unit tests + integration tests on tiny dataset
- Full suite (15 min): All tests on all scenarios
- GitHub Actions workflow for automated testing
- Performance baseline tracking

---

## Directory Structure

```
docs/test/
├── README.md                              (this file)
├── 01-data-feeder-design.md              (DataFeeder API & usage)
├── 02-integration-pipeline-design.md     (Integration test specifications)
├── 03-automation-framework.md            (CI/CD strategy & workflow)
└── diagrams/                             (PlantUML diagrams)
    ├── 01-data-feeder-architecture.puml
    ├── 02-data-flow.puml
    ├── 03-integration-pipeline-flow.puml
    ├── 04-test-categories.puml
    ├── 05-failure-response.puml
    └── README.md (diagram reference)
```

---

## Quick Start

### Running Tests Locally

```bash
# Install dependencies
pip install -e ".[dev]"

# Run unit tests only (fast, ~30 sec)
pytest tests/unit/ -v

# Run integration tests on tiny dataset (~1 min)
pytest tests/integration/ -m "integration_tiny" -v

# Run full integration suite (all scenarios, ~15 min)
pytest tests/integration/ -m "integration" -v

# Run with specific marker
pytest tests/ -m integration_small -v
```

### Using DataFeeder in Your Tests

```python
from tests.data_provisioner import DataFeeder

@pytest.fixture(scope="module")
def feeder():
    return DataFeeder(seed=42)

def test_pipeline_with_data(feeder, tmp_path):
    scenario = feeder.get_scenario("small_binary")
    csv_path = scenario.to_csv(tmp_path / "test.csv")
    
    # Run pipeline with test data
    result = subprocess.run([
        "python", "-m", "scripts.run_pipeline",
        "--dataset", str(csv_path),
        "--output-dir", str(tmp_path / "output")
    ], capture_output=True)
    
    assert result.returncode == 0
    assert (tmp_path / "output" / "tiny_ids_tnn.c").exists()
```

---

## Key Design Decisions

### Data-Driven Testing
- Scenarios defined upfront with known characteristics (sample counts, seeds)
- Reproducible across runs and environments
- Supports testing edge cases (extreme imbalance, minimal data, etc.)

### Full Pipeline Validation
- Tests run the complete `run_pipeline.py` script, not individual functions
- Validates real outputs (C code, TFLite models, metrics)
- Catches integration issues missed by unit testing

### Performance-Conscious CI/CD
- **Fast suite** (5 min): Early feedback on every commit
- **Full suite** (15 min): Comprehensive validation on pull requests
- Clear separation enables development velocity without sacrificing coverage

### Pytest Markers for Organization
- `@pytest.mark.integration_tiny`, `integration_small`, `integration_medium`, `integration_large`
- `@pytest.mark.unit`, `@pytest.mark.integration`
- `@pytest.mark.performance`, `@pytest.mark.slow`

---

## Test Organization

| Category | Count | Time | When |
|----------|-------|------|------|
| Unit | 84 | 45s | Every commit |
| Integration (tiny) | 3 | 1 min | Every commit (fast suite) |
| Integration (full) | 5 | 10 min | Pull requests (full suite) |
| Performance | 5 | 2 min | Pull requests |
| **Total** | **97** | **~15 min** | Full validation |

## Implementation Status

The testing framework is **fully designed** and **ready for implementation**.

---

## Common Tasks

### Adding a New Test Scenario

Edit `tests/data_provisioner.py`:
```python
class DataFeederConfig:
    SCENARIOS = {
        ...existing scenarios...
        "custom_scenario": ScenarioConfig(
            n_normal=1000,
            n_attack=200,
            seed=12345,
            window_size=50
        )
    }
```

### Running a Single Integration Test

```bash
pytest tests/integration/test_pipeline_outputs.py::test_c_code_compiles -v
```

### Running Only Performance Tests

```bash
pytest tests/ -m performance -v
```

---

## CI/CD Integration

### Fast Suite (Every Commit)
```bash
pytest tests/unit/ -v
pytest tests/integration/ -m "integration_tiny" -v
```

### Full Suite (Pull Requests)
```bash
pytest tests/ -m "not slow" -v
```

---

## File References

For detailed specifications, consult:
- **DataFeeder API**: See [01-data-feeder-design.md](01-data-feeder-design.md#data-feeder-class-design)
- **Integration Test Specs**: See [02-integration-pipeline-design.md](02-integration-pipeline-design.md#integration-test-specifications)
- **CI/CD Configuration**: See [03-automation-framework.md](03-automation-framework.md#github-actions-workflow)

---

For technical architecture and detailed design rationale, see individual design documents.
