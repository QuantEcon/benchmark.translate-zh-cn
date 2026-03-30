"""export command — Aggregate dataset and results into JSON for the dashboard site."""

from __future__ import annotations

import json
from pathlib import Path

from rich.panel import Panel

from qebench.models import Term
from qebench.utils.dataset import DATA_DIR, get_targets, load_all
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
    """Load XP data for all users."""
    xp_dir = _REPO_ROOT / "results" / "xp"
    if not xp_dir.exists():
        return []

    leaderboard = []
    for path in sorted(xp_dir.glob("*.json")):
        username = path.stem
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        leaderboard.append({
            "username": username,
            "total_xp": data.get("total", 0),
            "actions": data.get("actions", {}),
        })

    return sorted(leaderboard, key=lambda x: -x["total_xp"])


def _activity_feed() -> list[dict]:
    """Load recent translation attempts across all users."""
    translations_dir = _REPO_ROOT / "results" / "translations"
    if not translations_dir.exists():
        return []

    entries = []
    for path in translations_dir.glob("*.jsonl"):
        username = path.stem
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                record["username"] = username
                entries.append(record)

    # Sort by timestamp descending, take latest 50
    entries.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return entries[:50]


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
