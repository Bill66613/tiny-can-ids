---
mode: 'agent'
description: 'Multi-dimensional code review of current changes'
tools: ['terminal', 'codebase']
---

Perform a thorough code review of all current changes in this TinyML CAN bus IDS project.

## Steps

1. Run `git diff` to capture all modified files.
2. Review each dimension:

### Correctness
- Logic errors, off-by-one bugs, wrong array shapes/dtypes
- Incorrect quantization math (INT8 range [-128, 127])
- Broken feature engineering (46-feature vector order)

### Safety & Embedded
- Buffer overflows in generated C code templates
- Integer overflow in quantization
- Missing bounds checks, unsafe type conversions
- Division-by-zero in feature extraction
- No dynamic allocation (`malloc`, `calloc`, `realloc`) in C output templates

### Test Coverage
- For each changed function, verify corresponding tests exist in `tests/`
- Identify new code paths lacking test coverage
- Suggest specific test cases for untested paths

### Style & Consistency
- Type hints on public functions
- NumPy-style docstrings
- Import grouping: stdlib → third-party → local
- Consistent naming conventions

3. Group findings by severity:
   - **CRITICAL**: Must fix before merge
   - **WARNING**: Should fix
   - **SUGGESTION**: Nice to have

Include file paths with line numbers for each finding.
