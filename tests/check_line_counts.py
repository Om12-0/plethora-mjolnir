"""Acceptance check ensuring no python file in the repository exceeds 600 lines."""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main() -> int:
    over_limit = []
    checked = []

    for root, dirs, files in os.walk(ROOT):
        parts = set(root.split(os.sep))
        if parts & {".git", ".gemini", "__pycache__", "venv", ".venv", "dist", "build", "dist-installer"}:
            continue
        for f in files:
            if f.endswith(".py"):
                path = os.path.join(root, f)
                with open(path, "r", encoding="utf-8") as fh:
                    count = len(fh.readlines())
                rel = os.path.relpath(path, ROOT)
                checked.append((count, rel))
                if count > 600:
                    over_limit.append((count, rel))

    checked.sort(reverse=True)
    print(f"Checked {len(checked)} Python files in repository:")
    for count, rel in checked[:5]:
        print(f"  {count:4d} lines: {rel}")

    if over_limit:
        print(f"\nFAIL: {len(over_limit)} files exceed 600 lines limit:")
        for count, rel in over_limit:
            print(f"  EXCEEDS 600: {count:4d} lines: {rel}")
        return 1

    print(f"\nALL {len(checked)} FILES <= 600 LINES (max: {checked[0][0]} in {checked[0][1]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
