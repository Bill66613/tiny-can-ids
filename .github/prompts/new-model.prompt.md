---
mode: 'agent'
description: 'Guide for adding a new classifier type to the pipeline'
tools: ['terminal', 'codebase']
---

Add a new classifier type to the TinyML CAN bus IDS pipeline: {{input}}

## Checklist

### 1. Model Implementation (`can_ids/models/classifiers.py`)
- Add train/predict functions following existing patterns (see `train_logistic_regression`, `train_decision_tree`, `TinyNeuralNetwork`)
- Support both binary and multi-class classification modes
- Ensure model size stays within embedded memory budget

### 2. Quantization Support (`can_ids/models/compress.py`)
- Add INT8 quantization path for the new model
- Symmetric min-max quantization, per-layer scale factors
- Weights must fit in [-128, 127] range

### 3. C Code Export (`can_ids/deploy/c_export.py`)
- Add weight export function (header file with `static const int8_t` arrays)
- Add inference code generator (C source with `*_predict()` function)
- Follow naming convention: `tiny_ids_{abbrev}_weights.h` / `tiny_ids_{abbrev}_inference.c`
- No dynamic allocation, no floating-point in generated C code
- Input expects 46-feature vector

### 4. Pipeline Integration (`scripts/run_pipeline.py`)
- Add model to the training/evaluation loop
- Include in `--export-model` options
- Print metrics alongside existing models in the comparison table

### 5. Tests (`tests/`)
- Add training test in `test_models.py`
- Add export test in `test_export.py`
- Use existing fixtures and patterns

### 6. Documentation
- Update `CLAUDE.md`, `.github/AGENTS.md`, and `.github/copilot-instructions.md`

## Validation
Run `pytest tests/ -v` and `python -m scripts.run_pipeline --output-dir output/ --epochs 3`.
