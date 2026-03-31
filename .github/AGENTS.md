# AGENTS.md — tiny-can-ids

Instructions for AI coding agents (GitHub Copilot, Claude, etc.) working on this repository.

## Project Summary

TinyML CAN bus intrusion detection system. Pipeline: raw CAN data → feature engineering → model training → INT8 quantization → C code for ARM Cortex-M.

## Agent Roles

### Copilot Agent (VS Code)

- Use prompt files in `.github/prompts/` for structured workflows
- Follow `.github/copilot-instructions.md` for project context
- Prefer `agent` mode for multi-step tasks (test, review, pipeline, etc.)

### Claude Agent (Claude Code / CLI)

- Use slash commands in `.claude/commands/` for structured workflows
- Follow `CLAUDE.md` for project context, conventions, and gotchas
- Hooks in `.claude/settings.json` enforce safety (pre-commit tests, artifact validation)

### CI Agent (GitHub Actions)

- Workflow in `.github/workflows/ci.yml` runs tests + pipeline smoke on push/PR
- Matrix: Python 3.9, 3.11, 3.12
- Pipeline smoke verifies output artifacts exist

## Build & Test

```bash
pip install -e ".[dev]"
pytest tests/ -v
python -m scripts.run_pipeline --output-dir output/ --window-size 20 --epochs 5
```

## Helper Scripts

```bash
# Validate generated C code for embedded compliance
python .github/scripts/validate_c_output.py --output-dir output/

# Check model sizes against memory budget
python .github/scripts/check_model_size.py --output-dir output/

# Run full local CI (tests + pipeline + validation)
python .github/scripts/local_ci.py
```

## Critical Constraints

1. **43-feature vector**: The feature order (22 ID freq + 4 timing + 17 payload) is hardcoded in both Python (`build_feature_matrix()`) and generated C code. Never reorder without updating both.
2. **Memory budget**: NN ~0.8KB INT8, DT ~2KB, LR ~1KB. Do not add layers or increase hidden sizes without justification.
3. **No dynamic allocation in C**: Generated `.h` and `.c` files must use only `static const` arrays and stack variables. No `malloc`, no `printf`.
4. **INT8 range**: Quantized weights must be in `[-128, 127]`. Quantization uses symmetric min-max per-layer scaling.
5. **TFLite compatibility**: `export_to_tflite()` uses representative dataset calibration for full-integer quantization.

## Module Guide

| Module | Purpose | Key Functions |
|--------|---------|---------------|
| `can_ids/data/loader.py` | Load CSVs + synthetic data | `load_can_dataset()`, `generate_synthetic_can_data()`, `preprocess_can_data()` |
| `can_ids/features/engineer.py` | Sliding-window features | `build_feature_matrix()`, `extract_id_frequency_features()` |
| `can_ids/models/classifiers.py` | Train classifiers | `train_logistic_regression()`, `train_decision_tree()`, `TinyNeuralNetwork` |
| `can_ids/models/compress.py` | INT8 quantization + pruning | `quantize_weights()`, `ModelQuantizer` |
| `can_ids/models/export.py` | TFLite conversion | `export_to_tflite()`, `run_tflite_inference()` |
| `can_ids/deploy/c_export.py` | C code generation | `export_weights_to_c_header()`, `generate_inference_c_code()` |
| `scripts/run_pipeline.py` | CLI entry point | `main()` |

## Code Conventions

- Type hints on all public function signatures
- NumPy-style docstrings on all public functions
- Imports grouped: stdlib → third-party → local (blank lines between groups)
- Tests use `pytest.fixture(scope="module")` for expensive setup, `tmp_path` for file I/O

## Classification Modes

- **Binary**: Normal (0) vs Attack (1)
- **Multi-class**: Normal (0), DoS (1), Fuzzy (2), Gear (3), RPM (4)

## Before Submitting Changes

1. Run `pytest tests/ -v` — all tests must pass
2. Run `python -m scripts.run_pipeline --output-dir output/` — pipeline must complete end-to-end
3. Verify generated C files compile conceptually (no syntax errors in templates)
4. Check model size stays within budget
5. Ensure no new dependencies unless absolutely necessary
