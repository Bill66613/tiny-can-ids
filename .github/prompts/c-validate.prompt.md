---
mode: 'agent'
description: 'Validate generated C inference code for embedded deployment'
tools: ['terminal', 'codebase']
---

Validate the generated C code for correctness and embedded deployment readiness.

## Files to Check

Read all C files in `output/`:
- `tiny_ids_tnn_weights.h` / `tiny_ids_tnn_inference.c` (neural network)
- `tiny_ids_lr_weights.h` / `tiny_ids_lr_inference.c` (logistic regression)
- `tiny_ids_dt_weights.h` / `tiny_ids_dt_inference.c` (decision tree)

## Validation Criteria

### Header Files (.h)
- [ ] Include guards present (`#ifndef` / `#define` / `#endif`)
- [ ] All weight arrays are `static const int8_t`
- [ ] Scale factors defined as `#define` macros
- [ ] No `#include` of non-standard headers
- [ ] Array sizes match expected dimensions (46-feature input)
- [ ] All weight values in INT8 range [-128, 127]

### Source Files (.c)
- [ ] `*_predict()` function exists with correct signature
- [ ] Helper functions (`_relu`, `_sigmoid`, `_softmax`) are `static`
- [ ] No dynamic allocation (`malloc`, `calloc`, `realloc`, `free`)
- [ ] No `printf`, `fprintf`, or I/O calls
- [ ] No floating-point arithmetic (pure integer inference)
- [ ] Layer dimensions consistent with header weights
- [ ] Input size matches 46-feature vector
- [ ] Output matches classification mode (1 for binary, 5 for multi-class)

### Embedded Compliance
- [ ] No standard library dependencies beyond `<stdint.h>`
- [ ] All variables are stack-allocated or static const
- [ ] Suitable for bare-metal ARM Cortex-M deployment
- [ ] No undefined behavior (signed overflow, out-of-bounds access)

## Report

List any violations found with file, line number, and severity (CRITICAL / WARNING).
