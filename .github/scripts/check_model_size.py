#!/usr/bin/env python3
"""Check model sizes against TinyML memory budget.

Usage:
    python .github/scripts/check_model_size.py [--output-dir output/]

Budget:
    - TinyNeuralNetwork: ~0.8KB INT8
    - Decision Tree: ~2KB
    - Logistic Regression: ~1KB
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Size budgets in bytes
SIZE_BUDGETS = {
    "tnn": ("TinyNeuralNetwork", 1024),  # ~0.8KB + margin
    "lr": ("LogisticRegression", 1536),  # ~1KB + margin
    "dt": ("DecisionTree", 2560),  # ~2KB + margin
}


def check_sizes(output_dir: Path) -> list[str]:
    """Check generated C files against size budgets."""
    issues: list[str] = []

    for abbrev, (name, budget) in SIZE_BUDGETS.items():
        header = output_dir / f"tiny_ids_{abbrev}_weights.h"
        source = output_dir / f"tiny_ids_{abbrev}_inference.c"

        if not header.exists():
            issues.append(f"{name}: weights header not found")
            continue

        header_size = header.stat().st_size
        source_size = source.stat().st_size if source.exists() else 0
        total = header_size + source_size

        status = "✓" if header_size <= budget else "✗ OVER BUDGET"
        print(
            f"  {name:25s}  weights: {header_size:5d}B  "
            f"code: {source_size:5d}B  total: {total:5d}B  "
            f"budget: {budget:5d}B  {status}"
        )

        if header_size > budget:
            issues.append(
                f"{name}: weights {header_size}B exceeds budget {budget}B "
                f"(over by {header_size - budget}B)"
            )

    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Check model sizes against budget")
    parser.add_argument("--output-dir", default="output/", help="Output directory")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    if not output_dir.exists():
        print(f"Output directory {output_dir} does not exist. Run the pipeline first.")
        return 1

    print("Model Size Check")
    print("=" * 70)
    issues = check_sizes(output_dir)

    if issues:
        print(f"\n{len(issues)} budget violation(s):")
        for issue in issues:
            print(f"  ✗ {issue}")
        return 1

    print("\nAll models within budget ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
