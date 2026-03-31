---
mode: 'agent'
description: 'Run the ML pipeline end-to-end and validate outputs'
tools: ['terminal', 'codebase']
---

Run the full TinyML pipeline and validate all generated artifacts.

## Steps

1. Run the pipeline:
   ```bash
   python -m scripts.run_pipeline --output-dir output/ --window-size 20 --epochs 5
   ```

2. Verify all expected output artifacts exist:
   - `tiny_ids_tnn_weights.h` / `tiny_ids_tnn_inference.c` (neural network)
   - `tiny_ids_lr_weights.h` / `tiny_ids_lr_inference.c` (logistic regression)
   - `tiny_ids_dt_weights.h` / `tiny_ids_dt_inference.c` (decision tree)

3. Validate generated C code:
   - `.h` files: include guards, `static const int8_t` arrays, `#define` scale macros
   - `.c` files: `*_predict()` function, no `malloc`/`free`, dimensions match 46-feature input
   - All weight values in INT8 range [-128, 127]
   - Layer dimensions consistent between header and source

4. Parse classification metrics from pipeline output:
   - Check accuracy, precision, recall for each class
   - Flag any metric below 0.80
   - Compare binary vs multi-class performance

5. Report a dashboard with pipeline status, model sizes, metrics summary, and C code validation results.
