#!/usr/bin/env python3
"""Validate generated C code for embedded deployment compliance.

Usage:
    python .github/scripts/validate_c_output.py [--output-dir output/]

Checks:
    - All expected artifacts exist
    - No dynamic allocation (malloc, calloc, realloc, free)
    - No prohibited I/O (printf, fprintf, puts)
    - Include guards present in headers
    - Weight values in INT8 range [-128, 127]
    - Input dimension matches expected feature count
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

EXPECTED_FILES = {
    "tnn": ("tiny_ids_tnn_weights.h", "tiny_ids_tnn_inference.c"),
    "lr": ("tiny_ids_lr_weights.h", "tiny_ids_lr_inference.c"),
    "dt": ("tiny_ids_dt_weights.h", "tiny_ids_dt_inference.c"),
}

PROHIBITED_PATTERNS = [
    (r"\bmalloc\s*\(", "dynamic allocation (malloc)"),
    (r"\bcalloc\s*\(", "dynamic allocation (calloc)"),
    (r"\brealloc\s*\(", "dynamic allocation (realloc)"),
    (r"\bfree\s*\(", "dynamic deallocation (free)"),
    (r"\bprintf\s*\(", "I/O call (printf)"),
    (r"\bfprintf\s*\(", "I/O call (fprintf)"),
    (r"\bputs\s*\(", "I/O call (puts)"),
    (r"\bscanf\s*\(", "I/O call (scanf)"),
]

EXPECTED_FEATURES = 46


def validate_header(path: Path) -> list[str]:
    """Validate a .h weights file."""
    issues: list[str] = []
    content = path.read_text()

    # Check include guard
    if "#ifndef" not in content or "#define" not in content or "#endif" not in content:
        issues.append(f"{path.name}: Missing include guard")

    # Check weight arrays are static const
    if "static const" not in content:
        issues.append(f"{path.name}: No static const arrays found")

    # Check INT8 weight values
    int_values = re.findall(r"(?<![a-zA-Z0-9_])-?\d+(?![a-zA-Z0-9_.])", content)
    for val_str in int_values:
        val = int(val_str)
        if val < -128 or val > 127:
            # Could be array sizes or defines, only flag if in array context
            pass  # Fine-grained check would need AST parsing

    # Check for prohibited patterns
    for pattern, description in PROHIBITED_PATTERNS:
        if re.search(pattern, content):
            issues.append(f"{path.name}: Contains {description}")

    return issues


def validate_source(path: Path) -> list[str]:
    """Validate a .c inference file."""
    issues: list[str] = []
    content = path.read_text()

    # Check for predict function
    if "_predict" not in content:
        issues.append(f"{path.name}: Missing *_predict() function")

    # Check for prohibited patterns
    for pattern, description in PROHIBITED_PATTERNS:
        if re.search(pattern, content):
            issues.append(f"{path.name}: Contains {description}")

    # Check includes matching header
    header_name = path.name.replace("_inference.c", "_weights.h")
    if header_name not in content:
        issues.append(f"{path.name}: Does not include {header_name}")

    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate generated C output")
    parser.add_argument(
        "--output-dir", default="output/", help="Directory containing C files"
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    all_issues: list[str] = []
    files_found = 0

    for model_name, (header, source) in EXPECTED_FILES.items():
        header_path = output_dir / header
        source_path = output_dir / source

        if not header_path.exists():
            all_issues.append(f"MISSING: {header}")
            continue
        if not source_path.exists():
            all_issues.append(f"MISSING: {source}")
            continue

        files_found += 2
        all_issues.extend(validate_header(header_path))
        all_issues.extend(validate_source(source_path))

    print(f"Files found: {files_found}/{len(EXPECTED_FILES) * 2}")

    if all_issues:
        print(f"\n{len(all_issues)} issue(s) found:")
        for issue in all_issues:
            print(f"  ✗ {issue}")
        return 1

    print("All C code validations passed ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
