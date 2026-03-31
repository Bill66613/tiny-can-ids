#!/usr/bin/env python3
"""Quick local CI check — runs tests, pipeline smoke, and code quality.

Usage:
    python .github/scripts/local_ci.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def run_cmd(label: str, cmd: list[str], timeout: int = 300) -> tuple[bool, str]:
    """Run a command and return (success, output)."""
    print(f"\n{'─' * 60}")
    print(f"  {label}")
    print(f"{'─' * 60}")
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = result.stdout + result.stderr
        success = result.returncode == 0
        if not success:
            print(output[-500:] if len(output) > 500 else output)
        return success, output
    except subprocess.TimeoutExpired:
        return False, f"TIMEOUT after {timeout}s"
    except FileNotFoundError:
        return False, f"Command not found: {cmd[0]}"


def main() -> int:
    results: dict[str, bool] = {}

    # 1. Tests
    ok, out = run_cmd(
        "Running tests...",
        [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=short"],
    )
    results["Tests"] = ok

    # 2. Pipeline smoke test
    ok, out = run_cmd(
        "Running pipeline smoke test...",
        [
            sys.executable, "-m", "scripts.run_pipeline",
            "--output-dir", "output/",
            "--window-size", "20",
            "--epochs", "3",
        ],
    )
    results["Pipeline"] = ok

    # 3. C code validation
    validator = Path(".github/scripts/validate_c_output.py")
    if validator.exists():
        ok, out = run_cmd(
            "Validating C output...",
            [sys.executable, str(validator), "--output-dir", "output/"],
        )
        results["C Validation"] = ok

    # 4. Model size check
    size_checker = Path(".github/scripts/check_model_size.py")
    if size_checker.exists():
        ok, out = run_cmd(
            "Checking model sizes...",
            [sys.executable, str(size_checker), "--output-dir", "output/"],
        )
        results["Model Sizes"] = ok

    # Summary
    print(f"\n{'═' * 60}")
    print("  CI Summary")
    print(f"{'═' * 60}")
    all_pass = True
    for check, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {check:20s}  {status}")
        if not passed:
            all_pass = False

    overall = "PASS" if all_pass else "FAIL"
    print(f"\n  Overall: {overall}")
    print(f"{'═' * 60}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
