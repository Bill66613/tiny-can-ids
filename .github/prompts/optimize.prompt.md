---
mode: 'agent'
description: 'Analyze model and code for size/speed optimizations'
tools: ['terminal', 'codebase']
---

Analyze the TinyML pipeline for optimization opportunities across quantization, architecture, features, and generated C code.

## Analysis Areas

### Quantization
- Read `can_ids/models/compress.py` and `can_ids/models/export.py`
- Analyze INT8 vs FP32 weight distribution per layer
- Quantization error (max absolute difference after round-trip)
- Whether per-channel quantization would improve accuracy
- Scale factor magnitudes and potential precision loss

### Model Architecture
- Read `can_ids/models/classifiers.py`
- Current NN parameter count per layer
- Whether hidden sizes (32, 16) can be reduced without significant accuracy loss
- Decision tree depth vs accuracy tradeoff
- Logistic regression feature coefficient magnitudes

### Feature Importance
- Read `can_ids/features/engineer.py`
- Which of the 46 features have near-zero variance or near-zero model coefficients
- Whether any feature groups (ID freq, timing, payload, rate/novelty) could be pruned
- Correlation between features (redundancy)
- Impact on C code size if features are removed

### C Code Efficiency
- Read `can_ids/deploy/c_export.py` and `output/tiny_ids_tnn_inference.c`
- Loop unrolling opportunities
- Unnecessary multiplications (by 1.0 scale factors)
- Memory layout for cache efficiency on Cortex-M
- Whether CMSIS-NN kernels could replace manual inference code

## Output

Prioritized recommendations:
1. **Quick wins** — High impact, low effort
2. **Medium effort** — Require code changes but significant gains
3. **Long-term** — Architectural improvements for future versions

Include estimated memory savings for each recommendation.
