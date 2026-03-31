# Review

Perform a thorough multi-dimensional code review of current changes using parallel sub-agents.

## Step 1: Gather context

Run `git diff` to capture all current changes. Identify which files are modified.

## Step 2: Launch parallel review agents

Use the Agent tool to launch these **in parallel** (all in one message with multiple Agent calls):

1. **Correctness agent** — Review all changed Python files for logic errors, off-by-one bugs, wrong array shapes/dtypes, incorrect quantization math, broken feature engineering. Read each changed file fully before reviewing.

2. **Safety & embedded agent** — Review for: buffer overflows in generated C code templates, integer overflow in quantization (INT8 range [-128,127]), missing bounds checks, unsafe type conversions, potential division-by-zero in feature extraction. Also check that no dynamic allocation (`malloc`, `calloc`, `realloc`) appears in C output templates.

3. **Test coverage agent** — For each changed function, check if corresponding tests exist in `tests/`. Identify any new code paths that lack test coverage. Suggest specific test cases for untested paths.

4. **Style & consistency agent** — Check type hints on public functions, NumPy-style docstrings, import grouping (stdlib → third-party → local), consistent naming. Compare against existing code patterns in unchanged files.

## Step 3: Synthesize

After all agents return, compile findings into a single report grouped by severity:

- **CRITICAL**: Must fix before merge (correctness, safety, constraint violations)
- **WARNING**: Should fix (missing tests, potential edge cases)
- **SUGGESTION**: Nice to have (style, documentation improvements)

Include file paths with line numbers for each finding.
