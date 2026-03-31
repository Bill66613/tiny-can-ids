---
mode: 'agent'
description: 'Plan and implement a new feature with constraint checking'
tools: ['terminal', 'codebase']
---

Implement a new feature in the TinyML CAN bus IDS pipeline: {{input}}

## Workflow

### Phase 1: Research
- Search the codebase for files, functions, and patterns related to the feature
- Identify which modules need changes and what existing code can be reused
- Analyze TinyML constraint impact:
  - Memory budget: NN ~0.8KB INT8, DT ~2KB, LR ~1KB
  - 46-feature vector compatibility
  - Generated C code compatibility
  - INT8 quantization range [-128, 127]
- Review existing tests to understand testing patterns

### Phase 2: Plan
Create an implementation plan listing:
- Files to modify (with specific functions)
- New files to create (only if absolutely necessary)
- Test cases to add
- Constraint mitigations needed

### Phase 3: Implement
Follow project conventions:
- Type hints on all public function signatures
- NumPy-style docstrings on all public functions
- Import ordering: stdlib → third-party → local
- Module-scoped fixtures for expensive test setup

### Phase 4: Validate
- Run `pytest tests/ -v` and verify all tests pass
- If the feature changes the model or features, also run:
  ```bash
  python -m scripts.run_pipeline --output-dir output/ --window-size 20 --epochs 3
  ```
