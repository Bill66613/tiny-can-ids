# CLAUDE.md — tiny-can-ids

## Project Overview

TinyML-based CAN bus intrusion detection system for resource-constrained automotive embedded systems (TCUs/MCUs). End-to-end ML pipeline: raw CAN data → feature engineering → model training → INT8 quantization → C code deployment for ARM Cortex-M.

## Architecture

```
can_ids/
  data/       → Data loading (Car Hacking Dataset CSVs) & synthetic generation
  features/   → Sliding-window feature extraction (43 features: 22 ID freq + 4 timing + 17 payload)
  models/     → Classifiers (LogReg, DecisionTree, TinyNeuralNetwork), compression (INT8 quant, pruning), TFLite export
  deploy/     → C code generation (weights header + inference source)
scripts/      → run_pipeline.py (CLI entry point)
tests/        → pytest test suite (test_data, test_features, test_models, test_export)
output/       → Generated artifacts (.tflite, .h, .c)
```

## Tech Stack

- **Python** ≥ 3.9 | **Build**: setuptools via pyproject.toml
- **Core deps**: numpy ≥ 1.24, pandas ≥ 2.0, scikit-learn ≥ 1.3, tensorflow ≥ 2.13
- **Test**: pytest ≥ 7.0
- **Deploy target**: ARM Cortex-M via generated C code (`arm-none-eabi-gcc`)

## Key Commands

```bash
# Install
pip install -e ".[dev]"

# Run full pipeline (synthetic data)
python -m scripts.run_pipeline --output-dir output/

# Run with real dataset
python -m scripts.run_pipeline --dataset path/to/data.csv --output-dir output/
python -m scripts.run_pipeline --dataset-dir path/to/attack_csvs/ --output-dir output/

# Tests
pytest tests/ -v

# Single test file
pytest tests/test_models.py -v
```

## Conventions

- **Classification modes**: Binary (normal vs attack) and multi-class (Normal=0, DoS=1, Fuzzy=2, Gear=3, RPM=4)
- **Feature matrix**: Always 43 columns — do not change column order without updating C export
- **Neural net arch**: Input→Dense(32,ReLU)→Dense(16,ReLU)→Output (sigmoid binary / softmax multi-class)
- **Quantization**: Symmetric min-max INT8, per-layer scale factors stored as `#define` in C header
- **Generated C code**: `tiny_ids_weights.h` (static const int8_t arrays) + `tiny_ids_inference.c` (tiny_ids_predict function)
- **Tests**: Use `pytest.fixture(scope="module")` for expensive setup, `tmp_path` for file I/O tests

## Code Style

- Type hints on all public function signatures
- Docstrings on all public functions (NumPy-style)
- Imports: stdlib → third-party → local (grouped with blank lines)
- No linter/formatter enforced yet — keep consistent with existing code

## Important Constraints

- **Memory budget**: Models must stay tiny — NN ~0.8KB INT8, DT ~2KB, LR ~1KB
- **No dynamic allocation in C output**: All arrays are static const, stack-based inference
- **Feature order matters**: The C inference code assumes a fixed 43-element input vector order matching `build_feature_matrix()` output
- **INT8 range**: Quantized weights must be in [-128, 127]
- **TFLite calibration**: `export_to_tflite()` uses representative dataset for full-integer quantization

## Gotchas

- Car Hacking Dataset CSVs have variable-width rows (DLC < 8 means fewer data columns) — `_read_variable_width_csv()` handles this
- Synthetic data generator uses seeded randomness — pass `seed=` for reproducibility
- The `output/` directory is gitignored — generated artifacts are not committed
- TFLite export requires tensorflow — use `--no-tflite` flag if tf is unavailable

## Agent Workflows (Slash Commands)

Custom commands in `.claude/commands/` are designed for parallel sub-agent execution:

| Command | Purpose | Sub-agents |
|---------|---------|------------|
| `/test` | Run tests, diagnose failures in parallel per module | 1 per failing test module |
| `/review` | Multi-dimensional code review | 4 parallel: correctness, safety, test coverage, style |
| `/pipeline` | Run pipeline + verify all outputs | 3 parallel: artifact check, C validation, metrics |
| `/optimize` | Analyze model/code for size/speed improvements | 4 parallel: quantization, architecture, features, C code |
| `/implement` | Plan + implement a feature with constraint checks | 3 parallel research agents, then sequential implementation |
| `/ci` | Full local CI check before pushing | 3 parallel: tests, pipeline smoke, code quality |
| `/pr` | Validate + create a pull request | 3 parallel pre-flight, then PR creation |
| `/diagnose` | Root-cause investigation of a bug | 3 parallel: reproduce, code search, recent changes |

### Agent Design Principles

- **Parallel by default**: Independent analyses always run as simultaneous sub-agents
- **Fail-fast**: Validation agents stop the workflow early if critical checks fail
- **Context isolation**: Each sub-agent gets a focused task to avoid context window bloat
- **User confirmation**: Destructive or external actions (push, PR create) always ask first
