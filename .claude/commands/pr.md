# PR — Create a Pull Request

Prepare and create a pull request with automated validation.

## Step 1: Pre-flight checks (parallel agents)

Launch these agents **in parallel**:

1. **Diff analysis agent** — Run `git diff develop...HEAD` (or `git diff` if on develop). Catalog all changed files, added/removed lines, and categorize changes (feature, bugfix, refactor, test, docs). Summarize what this PR accomplishes.

2. **Test validation agent** — Run `pytest tests/ -v --tb=short`. Confirm all tests pass. If any fail, report them and stop — do not create a PR with failing tests.

3. **Constraint validation agent** — If any model or feature code was changed, run `python -m scripts.run_pipeline --output-dir output/ --window-size 20 --epochs 3` to verify the pipeline still works end-to-end. Check model sizes stay within budget.

## Step 2: Generate PR content

Based on the diff analysis, generate:

- **Title**: Short, descriptive (under 70 chars)
- **Summary**: 1-3 bullet points of what changed and why
- **Changes list**: Grouped by module
- **TinyML checklist**: Pre-fill based on actual validation results

## Step 3: Ask user for confirmation

Present the generated PR title and body. Ask the user to confirm or edit before creating.

## Step 4: Create the PR

Only after user confirms:

1. Push the current branch if it has unpushed commits
2. Create the PR using `gh pr create` with the approved title and body
3. Report the PR URL
