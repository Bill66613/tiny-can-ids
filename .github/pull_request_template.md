# Pull Request Template

## Summary
<!-- 1-3 bullet points describing what this PR does -->

## Changes
<!-- List the key changes made -->

## TinyML Checklist

- [ ] Model size stays within budget (NN ~0.8KB INT8, DT ~2KB, LR ~1KB)
- [ ] No dynamic memory allocation in generated C code
- [ ] Feature vector order preserved (or C export updated if changed)
- [ ] INT8 quantization validated (weights in [-128, 127])
- [ ] Tests pass: `pytest tests/ -v`
- [ ] Pipeline runs end-to-end with synthetic data

## Test Plan
<!-- How was this tested? Include commands and key results -->

## Classification Metrics
<!-- If model changes: paste relevant classification_report output -->
