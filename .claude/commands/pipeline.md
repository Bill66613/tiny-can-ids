# Pipeline

Run the full ML pipeline and validate all outputs using parallel verification agents.

## Step 1: Run the pipeline

```bash
python -m scripts.run_pipeline --output-dir output/ --window-size 20 --epochs 5
```

Capture the full output including classification metrics and model sizes.

## Step 2: Launch parallel verification agents

After the pipeline completes, launch these agents **in parallel**:

1. **Artifact verification agent** — Check that all expected output files exist (`output/tiny_ids_model.tflite`, `output/tiny_ids_weights.h`, `output/tiny_ids_inference.c`). Read each file and verify:
   - `.h` file has include guard, `static const int8_t` arrays, `#define` scale macros
   - `.c` file has `tiny_ids_predict()` function, `_relu()` and `_sigmoid()` helpers, `#include "tiny_ids_weights.h"`
   - `.tflite` file exists and is non-empty

2. **C code validation agent** — Read the generated `.c` and `.h` files. Verify: no `malloc`/`free`/dynamic allocation, all arrays are `static const`, dimensions match the 43-feature input vector, layer dimensions are consistent between header and source, weight values are in INT8 range.

3. **Metrics analysis agent** — Parse the pipeline output for classification reports. Check accuracy, precision, recall for each class. Flag if any metric drops below 0.80. Compare binary vs multi-class performance if both were run.

## Step 3: Report

Compile a dashboard:

- Pipeline status (pass/fail)
- Model sizes (FP32 vs INT8, TFLite file size)
- Classification metrics summary
- C code validation results
- Any warnings or issues found
