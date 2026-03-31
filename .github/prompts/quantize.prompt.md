---
mode: 'agent'
description: 'Analyze INT8 quantization quality and model compression'
tools: ['terminal', 'codebase']
---

Analyze the INT8 quantization pipeline for the TinyML CAN bus IDS models.

## Analysis Steps

1. **Read quantization code** — Review `can_ids/models/compress.py` for the `ModelQuantizer` class and `quantize_weights()` function.

2. **Read export code** — Review `can_ids/models/export.py` for `export_to_tflite()` and representative dataset calibration.

3. **Run the pipeline** to generate fresh quantized models:
   ```bash
   python -m scripts.run_pipeline --output-dir output/ --window-size 20 --epochs 5
   ```

4. **Weight Distribution Analysis**:
   - Per-layer weight statistics (min, max, mean, std) before and after quantization
   - Histogram of quantized weight values
   - Scale factor magnitudes per layer
   - Dead weights (values quantized to zero) percentage

5. **Quantization Error**:
   - Max absolute error after float→INT8→float round-trip
   - Mean squared quantization error per layer
   - Layers with highest quantization noise

6. **Accuracy Impact**:
   - Compare FP32 vs INT8 accuracy on test set
   - Per-class precision/recall changes after quantization
   - Identify which attack types are most affected

## Recommendations

- Whether per-channel quantization would help
- Whether mixed precision (some layers FP16) is warranted
- Pruning opportunities (weights near zero that could be zeroed)
- Optimal hidden layer sizes to minimize quantization loss
