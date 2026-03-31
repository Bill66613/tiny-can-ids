---
mode: 'agent'
description: 'Validate changes and prepare a pull request'
tools: ['terminal', 'codebase', 'githubRepo']
---

Prepare and create a pull request for the current changes in this TinyML CAN bus IDS project.

## Pre-flight Checks

1. **Diff analysis** — Run `git diff` to catalog all changed files. Categorize changes (feature, bugfix, refactor, test, docs). Summarize what this PR accomplishes.

2. **Test validation** — Run `pytest tests/ -v --tb=short`. All tests must pass. Do not proceed if any test fails.

3. **Constraint validation** — If any model or feature code changed, run `python -m scripts.run_pipeline --output-dir output/ --window-size 20 --epochs 3` to verify end-to-end. Check model sizes stay within budget.

## PR Content

Generate the PR using the project template from `.github/pull_request_template.md`:
- **Title**: Short, descriptive (under 70 chars)
- **Summary**: 1-3 bullet points of what changed and why
- **Changes list**: Grouped by module
- **TinyML Checklist**: Pre-fill based on actual validation results
- **Test Plan**: Commands run and key results
- **Classification Metrics**: If model changes, include classification_report output

## Submission

Ask for confirmation before creating the PR. Push the current branch if it has unpushed commits.
