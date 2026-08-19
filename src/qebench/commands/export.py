"""export command — Aggregate dataset and results into JSON for the dashboard site."""

from __future__ import annotations

import json
from pathlib import Path

from rich.panel import Panel

from qebench.models import Term
from qebench.utils.dataset import get_targets, load_all
from qebench.utils.display import console

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
EXPORT_DIR = _REPO_ROOT / "docs" / "_static" / "dashboard" / "data"


def _domain_stats(terms: list, sentences: list, paragraphs: list) -> list[dict]:
    """Build per-domain entry counts."""
    counts: dict[str, dict[str, int]] = {}
    for entry in terms:
        d = entry.domain
        counts.setdefault(d, {"terms": 0, "sentences": 0, "paragraphs": 0})
        counts[d]["terms"] += 1
    for entry in sentences:
        d = entry.domain
        counts.setdefault(d, {"terms": 0, "sentences": 0, "paragraphs": 0})
        counts[d]["sentences"] += 1
    for entry in paragraphs:
        d = entry.domain
        counts.setdefault(d, {"terms": 0, "sentences": 0, "paragraphs": 0})
        counts[d]["paragraphs"] += 1

    return sorted(
        [{"domain": d, **c} for d, c in counts.items()],
        key=lambda x: -(x["terms"] + x["sentences"] + x["paragraphs"]),
    )


def _difficulty_stats(terms: list, sentences: list, paragraphs: list) -> dict[str, int]:
    """Count entries by difficulty level."""
    counts: dict[str, int] = {"basic": 0, "intermediate": 0, "advanced": 0}
    for entry in [*terms, *sentences, *paragraphs]:
        counts[entry.difficulty.value] = counts.get(entry.difficulty.value, 0) + 1
    return counts


def _xp_leaderboard() -> list[dict]:
    """Load XP data for all users.

    Each ``results/xp/*.json`` file is read independently: a malformed or
    unreadable one is reported and skipped so it cannot cost every other
    contributor their place on the leaderboard.
    """
    xp_dir = _REPO_ROOT / "results" / "xp"
    if not xp_dir.exists():
        return []

    leaderboard = []
    for path in sorted(xp_dir.glob("*.json")):
        username = path.stem
        try:
            # utf-8-sig also accepts a leading BOM, which Windows editors add
            # to otherwise perfectly valid UTF-8 files.
            with open(path, encoding="utf-8-sig") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            console.print(f"[yellow]warning:[/] skipping malformed XP file {path.name}: {e}")
            continue
        except (OSError, UnicodeDecodeError) as e:
            # open() raises OSError, and a file saved in another encoding
            # raises UnicodeDecodeError from json.load — neither is a
            # JSONDecodeError, so both need catching around the read itself.
            console.print(f"[yellow]warning:[/] skipping unreadable XP file {path.name}: {e}")
            continue
        if not isinstance(data, dict):
            console.print(f"[yellow]warning:[/] skipping XP file {path.name}: expected a JSON object")
            continue
        total_xp = data.get("total", 0)
        if isinstance(total_xp, bool) or not isinstance(total_xp, (int, float)):
            console.print(f"[yellow]warning:[/] skipping XP file {path.name}: 'total' is not a number")
            continue
        # The dashboard renders this with Object.entries(user.actions || {}),
        # and a JS string is truthy — "oops" would come out as "0: o · 1: o".
        # Drop the breakdown rather than the contributor: it is cosmetic, so
        # they keep their place on the leaderboard.
        actions = data.get("actions", {})
        if not isinstance(actions, dict):
            console.print(
                f"[yellow]warning:[/] XP file {path.name}: 'actions' is not an object, "
                f"showing an empty breakdown"
            )
            actions = {}
        leaderboard.append({
            "username": username,
            "total_xp": total_xp,
            "actions": actions,
        })

    return sorted(leaderboard, key=lambda x: -x["total_xp"])


def _activity_feed() -> list[dict]:
    """Load recent translation attempts across all users.

    A malformed line — or a whole unreadable file — is reported and skipped
    rather than aborting the export.  Records already read from a file that
    turns out to be unreadable partway through are kept.
    """
    translations_dir = _REPO_ROOT / "results" / "translations"
    if not translations_dir.exists():
        return []

    entries = []
    for path in translations_dir.glob("*.jsonl"):
        username = path.stem
        lineno = 0
        try:
            with open(path, encoding="utf-8-sig") as f:
                for lineno, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError as e:
                        console.print(
                            f"[yellow]warning:[/] skipping malformed line {lineno} in {path.name}: {e}"
                        )
                        continue
                    if not isinstance(record, dict):
                        console.print(
                            f"[yellow]warning:[/] skipping line {lineno} in {path.name}: expected a JSON object"
                        )
                        continue
                    record["username"] = username
                    entries.append(record)
        except (OSError, UnicodeDecodeError) as e:
            # Raised by open() and, for a decode error, by the iterator —
            # so it must be caught around the loop, not around json.loads.
            console.print(
                f"[yellow]warning:[/] {path.name} unreadable after {lineno} line(s), "
                f"skipping the rest: {e}"
            )
            continue

    # Sort by timestamp descending, take latest 50.  A record whose timestamp is
    # not a string (null, a number) sorts as if it had none rather than raising
    # TypeError and taking the whole export down.
    entries.sort(key=_timestamp_key, reverse=True)
    return entries[:50]


def _timestamp_key(entry: dict) -> str:
    ts = entry.get("timestamp", "")
    return ts if isinstance(ts, str) else ""


def _term_samples(terms: list[Term], per_domain: int = 3) -> list[dict]:
    """Pick a few sample terms per domain for the browse section."""
    by_domain: dict[str, list[dict]] = {}
    for t in terms:
        by_domain.setdefault(t.domain, [])
        if len(by_domain[t.domain]) < per_domain:
            by_domain[t.domain].append({
                "id": t.id,
                "en": t.en,
                "zh": t.zh,
                "difficulty": t.difficulty.value,
            })
    samples = []
    for domain in sorted(by_domain):
        samples.extend(by_domain[domain])
    return samples


def export() -> None:
    """Export dataset stats and results to JSON for the dashboard website."""
    terms, sentences, paragraphs = load_all()
    targets = get_targets()

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Coverage summary
    coverage = {
        "terms": {"current": len(terms), "target": targets.get("terms", 500)},
        "sentences": {"current": len(sentences), "target": targets.get("sentences", 100)},
        "paragraphs": {"current": len(paragraphs), "target": targets.get("paragraphs", 30)},
        "total": len(terms) + len(sentences) + len(paragraphs),
    }

    # 2. Domain breakdown
    domains = _domain_stats(terms, sentences, paragraphs)

    # 3. Difficulty distribution
    difficulty = _difficulty_stats(terms, sentences, paragraphs)

    # 4. XP leaderboard
    leaderboard = _xp_leaderboard()

    # 5. Recent activity
    activity = _activity_feed()

    # 6. Sample terms for browse
    samples = _term_samples(terms)

    # Write all export files
    exports = {
        "coverage.json": coverage,
        "domains.json": domains,
        "difficulty.json": difficulty,
        "leaderboard.json": leaderboard,
        "activity.json": activity,
        "samples.json": samples,
    }

    for filename, data in exports.items():
        path = EXPORT_DIR / filename
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")

    console.print()
    console.print(
        Panel(
            "\n".join(
                f"  [green]✓[/green] {name}: {_file_summary(data)}"
                for name, data in exports.items()
            ),
            title="[bold]Exported to docs/_static/dashboard/data/[/bold]",
            border_style="blue",
        )
    )
    console.print()


def _file_summary(data: object) -> str:
    """One-line summary of what was exported."""
    if isinstance(data, list):
        return f"{len(data)} entries"
    if isinstance(data, dict) and "total" in data:
        return f"{data['total']} total entries"
    if isinstance(data, dict):
        return f"{len(data)} keys"
    return "exported"
