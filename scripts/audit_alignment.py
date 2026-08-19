"""Audit en/zh alignment of seeded sentence and paragraph entries.

The seeder in ``seed_from_lectures.py`` pairs English and Chinese prose by
position within a heading section and validates the pair with
``_shared_markers``.  That validator accepts a pair when the two texts share
any single math span, citation or inline-code span, which is weak enough to
let genuinely different paragraphs through — an English table and an
unrelated Chinese sentence both containing ``$x_1$`` will pass.

A misaligned reference is worse than a missing one: ``qebench judge`` pairs a
model translation against ``entry.zh`` when only one model has output for an
entry, and ``reference_overlap`` scores every judgment against it.  Bad
references quietly corrupt Elo.

This script re-checks each seeded pair against signals that must survive a
faithful translation:

- **Length ratio** — Chinese renders English in roughly 0.4-0.6 of the
  characters.  Far below that means the reference is truncated or is a
  different, shorter passage.
- **Math spans** — ``$...$`` content is copied verbatim, never translated,
  so most of the source's math should reappear in the reference.
- **Reference targets** — the target of a ``{doc}``/``{eq}``/``{ref}`` role
  is an identifier.  Display text is translated; the target is not.

Run: uv run python scripts/audit_alignment.py
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "data"

# Chinese renders English in ~0.4-0.6 of the characters; well below that means
# the reference is not a translation of the whole source.
MIN_LENGTH_RATIO = 0.30

# The bar when every math span and reference target carried over.  That is
# direct evidence the pair corresponds, so verbose English is tolerated —
# but not a translation that keeps a marker and drops the prose around it.
MIN_LENGTH_RATIO_SUPPORTED = 0.20

# Fraction of the source's math spans that may go missing before the pair is
# treated as misaligned rather than merely reformatted.
MAX_MISSING_MATH = 0.5

_MATH = re.compile(r"\$[^$\n]+\$")
_ROLE = re.compile(r"\{(eq|doc|ref|numref|cite|any|term)\}`([^`]*)`")
_ROLE_TARGET = re.compile(r"<([^>]+)>\s*$")


def math_spans(text: str) -> set[str]:
    """Inline math spans, which a faithful translation copies verbatim."""
    return set(_MATH.findall(text))


def role_targets(text: str) -> set[tuple[str, str]]:
    """(role name, link target) pairs.

    For ``{doc}`display text <target>``` the target is the identifier; for a
    bare ``{eq}`label``` the whole body is the identifier.  Display text is
    expected to be translated, so it is deliberately excluded.
    """
    targets: set[tuple[str, str]] = set()
    for name, body in _ROLE.findall(text):
        match = _ROLE_TARGET.search(body)
        targets.add((name, match.group(1).strip() if match else body.strip()))
    return targets


def check_pair(en: str, zh: str) -> list[str]:
    """Return a list of alignment problems, empty when the pair looks sound."""
    problems: list[str] = []

    en_math = math_spans(en)
    missing_math: set[str] = set()
    if en_math:
        missing_math = en_math - math_spans(zh)
        if len(missing_math) / len(en_math) > MAX_MISSING_MATH:
            problems.append(f"{len(missing_math)}/{len(en_math)} math spans missing")

    en_roles = role_targets(en)
    missing_roles: set[tuple[str, str]] = set()
    if en_roles:
        missing_roles = en_roles - role_targets(zh)
        if missing_roles:
            names = ", ".join(sorted(f"{{{n}}}`{t}`" for n, t in missing_roles))
            problems.append(f"{len(missing_roles)}/{len(en_roles)} reference targets missing: {names}")

    # Length is the weakest of the three signals — English is often simply
    # more verbose than its translation.  When the pair carries markers and
    # every one survives, that is direct evidence of correspondence, so the
    # bar drops rather than disappearing: a pair that keeps its one math span
    # while dropping nine tenths of its prose is still worth flagging.
    has_markers = bool(en_math or en_roles)
    supported = has_markers and not missing_math and not missing_roles
    floor = MIN_LENGTH_RATIO_SUPPORTED if supported else MIN_LENGTH_RATIO
    ratio = len(zh) / max(len(en), 1)
    if ratio < floor:
        problems.append(f"length ratio {ratio:.2f} (expected >= {floor})")

    return problems


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
