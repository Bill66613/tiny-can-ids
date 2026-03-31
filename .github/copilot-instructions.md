# Copilot Instructions — tiny-can-ids

## Project Context

This is a TinyML CAN bus intrusion detection system for automotive embedded systems. The pipeline goes from raw CAN bus data to deployable C code for ARM Cortex-M microcontrollers.

## Key Technical Constraints

- **Memory budget**: Neural network must be ~0.8KB INT8. No model can exceed a few KB.
- **No dynamic memory in C output**: All generated C code uses static const arrays and stack-based computation.
- **Fixed feature vector**: 43 features in a specific order (22 ID frequency + 4 timing + 17 payload). Changing order breaks C inference code.
- **INT8 quantization**: Symmetric min-max, weights in [-128, 127], per-layer scale factors.

## Code Conventions

- Python 3.9+ with type hints on all public functions
- NumPy-style docstrings
- Import order: stdlib → third-party → local
- Tests use pytest with module-scoped fixtures for expensive setup
- Generated C code follows embedded C patterns: no malloc, no printf, pure integer arithmetic

## Architecture Decisions

- `can_ids/data/`: Handles both standard and variable-width CSV rows (DLC < 8)
- `can_ids/features/`: Sliding-window approach with configurable window size
- `can_ids/models/`: Three classifier types (LogReg, DecisionTree, TinyNeuralNetwork) with INT8 quantization
- `can_ids/deploy/`: C code generator producing `.h` (weights) and `.c` (inference function)
- Binary classification (normal/attack) and multi-class (Normal, DoS, Fuzzy, Gear, RPM)

## When Suggesting Changes

1. Always consider impact on the generated C code — feature changes cascade to deployment
2. Run tests after any modification: `pytest tests/ -v`
3. Keep models tiny — prefer simpler architectures
4. Maintain backward compatibility of the 43-feature vector unless explicitly redesigning
