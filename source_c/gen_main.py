#!/usr/bin/env python3
"""
gen_main.py — Generate src/main.c from src/main.c_template.

Scans src/models/ for files matching <attack>_ids_<model>_weights.h, extracts:
  - #define <ATTACK>_IDS_<MODEL>_WINDOW_SIZE <N>
  - int <attack>_ids_<model>_process_window(const CAN_Frame_t *window);

Then substitutes in the template:
  // ##TAG_1  →  #include "models/<file>.h" lines
  // ##TAG_2  →  handler table entry rows

Usage:
  python gen_main.py              # reads/writes relative to script location
  python gen_main.py --dry-run    # print result to stdout, do not write
"""

import argparse
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent  # source_c/
SRC_MODELS_DIR = SCRIPT_DIR / "src" / "models"
TEMPLATE_PATH = SCRIPT_DIR / "src" / "main.c_template"
OUTPUT_PATH = SCRIPT_DIR / "src" / "main.c"

_FILENAME_RE = re.compile(r"^([a-z][a-z0-9]*)_ids_([a-z][a-z0-9]*)_weights\.h$")
_WINDOW_SIZE_RE = re.compile(
    r"#define\s+([A-Z][A-Z0-9]*_IDS_[A-Z][A-Z0-9]*_WINDOW_SIZE)\s+\d+"
)
_PROCESS_WINDOW_RE = re.compile(
    r"void\s+([a-z][a-z0-9]*_ids_[a-z][a-z0-9]*_process_window)\s*\("
)


def scan_models(models_dir: Path) -> list[dict]:
    """Scan models_dir for *_ids_*_weights.h and return parsed metadata."""
    entries: list[dict] = []
    for h_file in sorted(models_dir.glob("*_ids_*_weights.h")):
        m = _FILENAME_RE.match(h_file.name)
        if not m:
            continue
        attack, model = m.group(1), m.group(2)
        content = h_file.read_text(encoding="utf-8")

        ws_match = _WINDOW_SIZE_RE.search(content)
        pw_match = _PROCESS_WINDOW_RE.search(content)

        if not ws_match:
            print(
                f"[WARN] {h_file.name}: no WINDOW_SIZE macro found — skipped",
                file=sys.stderr,
            )
            continue
        if not pw_match:
            print(
                f"[WARN] {h_file.name}: no process_window function found — skipped",
                file=sys.stderr,
            )
            continue

        entries.append(
            {
                "attack": attack,
                "model": model,
                "header": h_file.name,
                "window_size_macro": ws_match.group(1),
                "fn_name": pw_match.group(1),
            }
        )
    return entries


def build_tag1(entries: list[dict]) -> str:
    """Build the #include block for TAG_1."""
    return "\n".join(f'#include "models/{e["header"]}"' for e in entries)


def build_tag2(entries: list[dict]) -> str:
    """Build the handler table rows for TAG_2."""
    rows: list[str] = []
    for e in entries:
        attack_enum = f'ATTACK_{e["attack"].upper()}'
        model_enum = f'MODEL_{e["model"].upper()}'
        fn = e["fn_name"]
        ws = e["window_size_macro"]
        label = f'{e["attack"]}/{e["model"]}'
        rows.append(
            f"\t{{{attack_enum + ',':<14} {model_enum + ',':<12} "
            f"{fn + ',':<44} {ws + ',':<34} \"{label}\"}}"
            f","
        )
    return "\n".join(rows)


def generate(dry_run: bool = False) -> int:
    if not TEMPLATE_PATH.exists():
        print(f"Error: template not found: {TEMPLATE_PATH}", file=sys.stderr)
        return 1

    entries = scan_models(SRC_MODELS_DIR)
    if not entries:
        print(
            "Error: no model headers found in " + str(SRC_MODELS_DIR) + " — cannot generate main.c.",
            file=sys.stderr,
        )
        return 1

    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    result = template.replace("// ##TAG_1", build_tag1(entries))
    result = result.replace("// ##TAG_2", build_tag2(entries))

    if "// ##TAG_1" in result or "// ##TAG_2" in result:
        print("Error: one or more TAG markers were not replaced.", file=sys.stderr)
        return 1

    if dry_run:
        print(result, end="")
    else:
        OUTPUT_PATH.write_text(result, encoding="utf-8")
        print(f"Generated {OUTPUT_PATH} ({len(entries)} model(s)):")
        for e in entries:
            print(
                f"  {e['attack']}/{e['model']}  fn={e['fn_name']}  window={e['window_size_macro']}"
            )

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print generated output to stdout, do not write file",
    )
    args = parser.parse_args()
    return generate(dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
