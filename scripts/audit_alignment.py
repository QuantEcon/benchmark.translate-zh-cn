"""Audit en/zh alignment of seeded sentence and paragraph entries.

A CLI over :mod:`qebench.scoring.alignment`, which holds the rule itself and
documents the signals it checks.  The same rule gates seeding in
``seed_from_lectures.py`` and runs inside ``qebench validate``, so this
report and the data can only agree.

Use it to review the committed dataset — ``--show-text`` prints each flagged
pair so a human can judge whether it is genuinely misaligned or merely
verbose English, and ``--json`` dumps the findings for further processing.

Run: uv run python scripts/audit_alignment.py
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from qebench.scoring.alignment import (
    MAX_MISSING_MATH,
    MIN_LENGTH_RATIO,
    MIN_LENGTH_RATIO_SUPPORTED,
    check_pair,
    math_spans,
    role_targets,
)

DATA_DIR = Path(__file__).resolve().parents[1] / "data"

__all__ = [
    "MAX_MISSING_MATH",
    "MIN_LENGTH_RATIO",
    "MIN_LENGTH_RATIO_SUPPORTED",
    "audit",
    "audit_file",
    "check_pair",
    "math_spans",
    "role_targets",
]


def audit_file(path: Path) -> list[dict]:
    """Audit one seed file, returning a record per flagged entry."""
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    entries = raw["entries"] if isinstance(raw, dict) and "entries" in raw else raw

    flagged = []
    for entry in entries:
        problems = check_pair(entry.get("en", ""), entry.get("zh", ""))
        if problems:
            flagged.append({
                "id": entry.get("id", ""),
                "source": entry.get("source", ""),
                "problems": problems,
                "en": entry.get("en", ""),
                "zh": entry.get("zh", ""),
            })
    return flagged


def audit(data_dir: Path = DATA_DIR) -> dict[str, list[dict]]:
    """Audit every seeded sentence and paragraph file under *data_dir*."""
    results: dict[str, list[dict]] = {}
    for entry_type in ("sentences", "paragraphs"):
        flagged: list[dict] = []
        for path in sorted((data_dir / entry_type).glob("*.json")):
            flagged.extend(audit_file(path))
        results[entry_type] = flagged
    return results


def _count_entries(data_dir: Path, entry_type: str) -> int:
    total = 0
    for path in sorted((data_dir / entry_type).glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        entries = raw["entries"] if isinstance(raw, dict) and "entries" in raw else raw
        total += len(entries)
    return total


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR, help="Dataset directory to audit.")
    parser.add_argument("--json", type=Path, default=None, help="Write the full findings to this JSON file.")
    parser.add_argument("--show-text", action="store_true", help="Print the en/zh text of each flagged pair.")
    args = parser.parse_args()

    results = audit(args.data_dir)

    for entry_type, flagged in results.items():
        total = _count_entries(args.data_dir, entry_type)
        print(f"\n{entry_type}: {len(flagged)}/{total} flagged")
        for record in flagged:
            print(f"  {record['id']}  ({record['source']})")
            for problem in record["problems"]:
                print(f"      - {problem}")
            if args.show_text:
                print(f"      EN: {record['en'][:200]}")
                print(f"      ZH: {record['zh'][:200]}")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print(f"\nWrote {args.json}")

    flagged_total = sum(len(v) for v in results.values())
    print(f"\nTotal flagged: {flagged_total}")


if __name__ == "__main__":
    main()
