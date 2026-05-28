# Integration Test Pipeline Design

## Overview

Integration tests **run the full `run_pipeline.py` script** with different scenarios and **validate the output artifacts**. This ensures:
- End-to-end pipeline executes without errors
- All expected output files are generated
- Output files are valid (C code, TFLite, metrics)
- Metrics are reasonable (accuracy, model sizes)

---

## Integration Test Architecture

See [diagrams/03-integration-pipeline-flow.puml](diagrams/03-integration-pipeline-flow.puml) for the comprehensive flow showing:
- Scenario setup (4 size categories)
- Full pipeline execution
- Output validation (C files, TFLite, metrics, compilation)
- Pass/Fail outcomes

---

## Integration Test Scenarios

Each integration test runs the full pipeline with a different scenario and validates outputs:

| Scenario | Normal | Attack | Purpose |
|----------|--------|--------|---------|
| `tiny_binary` | 100 | 20 | Fast smoke test (1 second) |
| `small_binary` | 500 | 100 | Quick validation (5 seconds) |
| `medium_binary` | 1500 | 300 | Standard validation (15 seconds) |
| `large_binary` | 5000 | 1000 | Stress test (45 seconds) |

---

## Integration Test Specifications

### **Test 1: Pipeline Runs (tiny_binary)**

**Purpose:** Validate pipeline executes without errors on tiny dataset

**Test Name:** `test_integration_pipeline_runs_tiny()`

**Execution:**
```python
def test_integration_pipeline_runs_tiny(feeder, tmp_path):
    scenario = feeder.get_scenario("tiny_binary")
    csv_path = scenario.to_csv(tmp_path / "tiny.csv")
    output_dir = tmp_path / "output"
    
    # Run pipeline
    result = subprocess.run([
        "python", "-m", "scripts.run_pipeline",
        "--dataset", str(csv_path),
        "--output-dir", str(output_dir)
    ], capture_output=True, text=True)
    
    assert result.returncode == 0  # Pipeline completed
    assert output_dir.exists()
```

**Validations:**
- Pipeline exits with code 0 (success)
- Output directory created
- No exceptions logged
- Execution time < 5 seconds

**Artifacts Checked:**
- `tiny_ids_tnn_weights.h` exists
- `tiny_ids_tnn.c` exists
- `tiny_ids_lr_weights.h` exists
- `tiny_ids_dt_weights.h` exists

---

### **Test 2: C Headers Valid (small_binary)**

**Purpose:** Validate generated C header files are syntactically correct

**Test Name:** `test_integration_c_headers_valid()`

**Execution:**
```python
def test_integration_c_headers_valid(feeder, tmp_path):
    scenario = feeder.get_scenario("small_binary")
    csv_path = scenario.to_csv(tmp_path / "small.csv")
    output_dir = tmp_path / "output"
    
    # Run pipeline
    subprocess.run([...], check=True)
    
    # Validate headers
    for header_file in output_dir.glob("tiny_ids_*.h"):
        content = header_file.read_text()
        assert "#ifndef" in content
        assert "#define" in content
        assert "#endif" in content
        assert "static const int8_t" in content
        assert "#include <stdint.h>" in content
```

**Validations:**
- Include guards present
- `static const` arrays defined
- `#define` scale factors present
- Shape macros defined
- Proper C syntax (basic checks)

**Files Checked:**
- `tiny_ids_tnn_weights.h`
- `tiny_ids_lr_weights.h`
- `tiny_ids_dt_weights.h`

---

### **Test 3: C Source Valid (small_binary)**

**Purpose:** Validate generated C source files are syntactically correct

**Test Name:** `test_integration_c_source_valid()`

**Execution:**
```python
def test_integration_c_source_valid(feeder, tmp_path):
    scenario = feeder.get_scenario("small_binary")
    csv_path = scenario.to_csv(tmp_path / "small.csv")
    output_dir = tmp_path / "output"
    
    # Run pipeline
    subprocess.run([...], check=True)
    
    # Validate source files
    for source_file in output_dir.glob("tiny_ids_*.c"):
        content = source_file.read_text()
        assert "#include" in content
        assert "float ids_predict" in content
        assert "static float _relu" in content or source_file.name != "tiny_ids_tnn.c"
        assert "malloc" not in content  # No dynamic allocation
```

**Validations:**
- Include statements present
- Predict function defined
- ReLU/Sigmoid functions present
- No `malloc` calls (static memory)
- Proper C syntax (basic checks)

**Files Checked:**
- `tiny_ids_tnn.c`
- `tiny_ids_lr.c`
- `tiny_ids_dt.c`

---

### **Test 4: C Code Compiles (medium_binary)**

**Purpose:** Validate C code actually compiles without errors

**Test Name:** `test_integration_c_code_compiles()`

**Execution:**
```python
def test_integration_c_code_compiles(feeder, tmp_path):
    scenario = feeder.get_scenario("medium_binary")
    csv_path = scenario.to_csv(tmp_path / "medium.csv")
    output_dir = tmp_path / "output"
    
    # Run pipeline
    subprocess.run([...], check=True)
    
    # Compile with arm-none-eabi-gcc (if available)
    compiler = shutil.which("arm-none-eabi-gcc")
    if not compiler:
        pytest.skip("arm-none-eabi-gcc not available")
    
    for source_file in output_dir.glob("tiny_ids_*.c"):
        header_file = source_file.with_suffix(".h")
        result = subprocess.run([
            compiler,
            "-c", str(source_file),
            "-I", str(output_dir),
            "-o", str(output_dir / source_file.with_suffix(".o").name),
            "-Wall", "-Werror"
        ], capture_output=True, text=True)
        
        assert result.returncode == 0, f"Compilation failed: {result.stderr}"
```

**Validations:**
- Compilation succeeds (no errors)
- No compilation warnings (-Wall enabled)
- Object file generated
- Object file size reasonable

**Files Checked:**
- `tiny_ids_tnn.c` → `tiny_ids_tnn.o`
- `tiny_ids_lr.c` → `tiny_ids_lr.o`
- `tiny_ids_dt.c` → `tiny_ids_dt.o`

---

### **Test 5: Model Sizes Reasonable (small_binary)**

**Purpose:** Validate quantized model files are within size budgets

**Test Name:** `test_integration_model_sizes_reasonable()`

**Execution:**
```python
def test_integration_model_sizes_reasonable(feeder, tmp_path):
    scenario = feeder.get_scenario("small_binary")
    csv_path = scenario.to_csv(tmp_path / "small.csv")
    output_dir = tmp_path / "output"
    
    # Run pipeline
    subprocess.run([...], check=True)
    
    # Check file sizes
    tnn_h = output_dir / "tiny_ids_tnn_weights.h"
    tnn_c = output_dir / "tiny_ids_tnn.c"
    
    assert tnn_h.stat().st_size < 5000  # ~5 KB for weights
    assert tnn_c.stat().st_size < 10000  # ~10 KB for inference code
```

**Size Budgets:**
- TNN weights header < 5 KB
- TNN source code < 10 KB
- LR weights + source < 3 KB
- DT weights + source < 8 KB

---

### **Test 6: TFLite File Valid (medium_binary)**

**Purpose:** Validate TFLite export is valid and compilable

**Test Name:** `test_integration_tflite_valid()`

**Execution:**
```python
def test_integration_tflite_valid(feeder, tmp_path):
    scenario = feeder.get_scenario("medium_binary")
    csv_path = scenario.to_csv(tmp_path / "medium.csv")
    output_dir = tmp_path / "output"
    
    # Run pipeline (without --no-tflite)
    subprocess.run([...], check=True)
    
    # Check TFLite file
    tflite_file = list(output_dir.glob("*.tflite"))
    assert len(tflite_file) > 0, "No .tflite file generated"
    
    size = tflite_file[0].stat().st_size
    assert size > 0, "TFLite file is empty"
    assert size < 50000, "TFLite file too large (> 50 KB)"
```

**Validations:**
- `.tflite` file exists
- File size > 0 bytes
- File size < 50 KB
- File is readable

---

### **Test 7: Metrics Reported (small_binary)**

**Purpose:** Validate pipeline generates metrics

**Test Name:** `test_integration_metrics_generated()`

**Execution:**
```python
def test_integration_metrics_generated(feeder, tmp_path):
    scenario = feeder.get_scenario("small_binary")
    csv_path = scenario.to_csv(tmp_path / "small.csv")
    output_dir = tmp_path / "output"
    
    # Run pipeline with captured output
    result = subprocess.run([...], capture_output=True, text=True)
    
    # Check metrics in stdout
    assert "Accuracy" in result.stdout or "accuracy" in result.stdout
    assert "F1" in result.stdout or "f1" in result.stdout
    assert "Model Comparison" in result.stdout
```

**Validations:**
- Accuracy metric logged
- F1 metric logged
- Comparison table printed
- All 3 models evaluated

---

### **Test 8: Full Pipeline Stress Test (large_binary)**

**Purpose:** Validate pipeline handles larger datasets

**Test Name:** `test_integration_pipeline_large_dataset()`

**Execution:**
```python
def test_integration_pipeline_large_dataset(feeder, tmp_path):
    scenario = feeder.get_scenario("large_binary")
    csv_path = scenario.to_csv(tmp_path / "large.csv")
    output_dir = tmp_path / "output"
    
    # Run pipeline
    start = time.time()
    result = subprocess.run([...], check=True, timeout=120)
    elapsed = time.time() - start
    
    # Validate all artifacts
    assert (output_dir / "tiny_ids_tnn.c").exists()
    assert (output_dir / "tiny_ids_lr.c").exists()
    assert (output_dir / "tiny_ids_dt.c").exists()
    
    # Check performance
    assert elapsed < 120, f"Pipeline took {elapsed} seconds (> 120s)"
```

**Validations:**
- Pipeline completes on large dataset
- All artifacts generated
- Execution time < 120 seconds
- No out-of-memory errors

---

## Test Organization

```python
# tests/integration/test_pipeline_outputs.py
import pytest
from pathlib import Path
import subprocess

@pytest.fixture
def feeder():
    from tests.data_provisioner import DataFeeder
    return DataFeeder(seed=42)

class TestPipelineOutputs:
    """Integration tests validating run_pipeline.py outputs"""
    
    def test_pipeline_runs_tiny(self, feeder, tmp_path):
        """Pipeline runs without errors on tiny dataset"""
        # See Test 1 above
        pass
    
    def test_c_headers_valid(self, feeder, tmp_path):
        """Generated C headers are syntactically valid"""
        # See Test 2 above
        pass
    
    def test_c_source_valid(self, feeder, tmp_path):
        """Generated C source is syntactically valid"""
        # See Test 3 above
        pass
    
    def test_c_code_compiles(self, feeder, tmp_path):
        """Generated C code compiles without errors"""
        # See Test 4 above
        pass
    
    def test_model_sizes_reasonable(self, feeder, tmp_path):
        """Model files are within size budgets"""
        # See Test 5 above
        pass
    
    def test_tflite_valid(self, feeder, tmp_path):
        """TFLite export is valid"""
        # See Test 6 above
        pass
    
    def test_metrics_generated(self, feeder, tmp_path):
        """Pipeline reports metrics"""
        # See Test 7 above
        pass
    
    def test_pipeline_large_dataset(self, feeder, tmp_path):
        """Pipeline handles larger datasets"""
        # See Test 8 above
        pass
```

---

## Test Execution Flow

See [diagrams/03-integration-pipeline-flow.puml](diagrams/03-integration-pipeline-flow.puml) for the detailed test execution sequence.

---

## Key Differences from Unit Tests

| Aspect | Unit Tests | Integration Tests |
|--------|-----------|------------------|
| **What runs** | Individual functions | Full `run_pipeline.py` script |
| **Input** | Synthetic arrays/DataFrames | Predefined scenarios (CSV) |
| **Validates** | Function logic | Pipeline outputs (files, artifacts) |
| **Speed** | Fast (< 1 sec each) | Medium (5-45 sec per test) |
| **Examples** | `test_extract_features()` | `test_c_code_compiles()` |

---

See [03-automation-framework.md](03-automation-framework.md) for CI/CD configuration details.
