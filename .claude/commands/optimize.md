# Optimize

Analyze the model compression and deployment pipeline for optimization opportunities using parallel analysis agents.

## Step 1: Run baseline

```bash
python -m scripts.run_pipeline --output-dir output/ --window-size 20 --epochs 5
```

## Step 2: Launch parallel analysis agents

After the pipeline finishes, launch these agents **in parallel**:

1. **Quantization analysis agent** — Read `can_ids/models/compress.py` and `can_ids/models/export.py`. Analyze:
   - INT8 vs FP32 weight distribution per layer
   - Quantization error (max absolute difference after round-trip)
   - Whether per-channel quantization would improve accuracy
   - Scale factor magnitudes and potential precision loss

2. **Model architecture agent** — Read `can_ids/models/classifiers.py`. Analyze:
   - Current NN parameter count per layer
   - Whether hidden sizes (32, 16) can be reduced without significant accuracy loss
   - Decision tree depth vs accuracy tradeoff
   - Logistic regression feature coefficient magnitudes (which features matter least)

3. **Feature importance agent** — Read `can_ids/features/engineer.py` and the pipeline output. Analyze:
   - Which of the 43 features have near-zero variance or near-zero model coefficients
   - Whether any feature groups (ID freq, timing, payload) could be pruned entirely
   - Correlation between features (redundancy)
   - Impact on C code size if features are removed

4. **C code efficiency agent** — Read `can_ids/deploy/c_export.py` and `output/tiny_ids_inference.c`. Analyze:
   - Loop unrolling opportunities
   - Unnecessary multiplications (by 1.0 scale factors)
   - Memory layout for cache efficiency on Cortex-M
   - Whether CMSIS-NN kernels could replace manual inference code

## Step 3: Recommendations

Compile findings into prioritized recommendations:

1. **Quick wins** — Changes with high impact and low effort
2. **Medium effort** — Require code changes but significant gains
3. **Long-term** — Architectural improvements for future versions

Include estimated memory savings for each recommendation.
