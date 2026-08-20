"""export command — Aggregate dataset and results into JSON for the dashboard site."""

from __future__ import annotations

import json
from pathlib import Path

from rich.panel import Panel

from qebench.models import Term
from qebench.scoring.formatting import formatting_score
from qebench.scoring.glossary import expected_translations, glossary_compliance
from qebench.scoring.ratings import (
    elo_eligible,
    load_judgment_records,
    recompute_elo,
    score_summary,
)
from qebench.utils.dataset import get_targets, load_all, load_glossary
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


def _ratings_export() -> dict:
    """Rebuild the model ratings from the committed judgment logs.

    ``results/elo.json`` is gitignored, so the cached ratings never left the
    machine that happened to be judging.  ``results/judgments/*.jsonl`` is
    committed, so recomputing here means CI derives the numbers from data the
    repository actually carries.

    Both granularities are exported because a label is either a bare model or
    ``model:prompt`` depending on when it was recorded, and neither ranking
    subsumes the other — see :mod:`qebench.scoring.ratings`.  The judgment
    counts travel with them so a reader can tell a ranking from noise.
    """
    records = load_judgment_records(_REPO_ROOT / "results" / "judgments")
    return {
        "by_model": [r.as_dict() for r in recompute_elo(records, by_prompt=False)],
        "by_model_prompt": [r.as_dict() for r in recompute_elo(records, by_prompt=True)],
        "scores_by_model": score_summary(records, by_prompt=False),
        "scores_by_model_prompt": score_summary(records, by_prompt=True),
        "judgments": {
            "total": len(records),
            "elo_eligible_by_model": sum(
                1 for r in records if elo_eligible(r, by_prompt=False)
            ),
            "elo_eligible_by_model_prompt": sum(
                1 for r in records if elo_eligible(r, by_prompt=True)
            ),
        },
    }


# formatting_score() returns three pass/fail checks and two 0-1 rates.
_BOOLEAN_CHECKS = ("directive_balance", "fence_consistency", "code_block_integrity")
_SCORE_CHECKS = ("fullwidth_punctuation", "directive_spacing")
_FORMATTING_KEYS = _BOOLEAN_CHECKS + _SCORE_CHECKS

# April's term runs predate the entry_type field — recover it from the id.
_ID_PREFIX_TYPES = {"term": "terms", "sent": "sentences", "para": "paragraphs"}


def _run_records() -> list[dict]:
    """Every usable record in ``results/model-outputs``.

    Tolerant in the same way as the other readers here: this runs in the
    docs-deploy workflow, so one malformed line must not fail the dashboard
    build for everyone.
    """
    outputs_dir = _REPO_ROOT / "results" / "model-outputs"
    if not outputs_dir.exists():
        return []

    records: list[dict] = []
    for path in sorted(outputs_dir.glob("*.jsonl")):
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
                    if isinstance(record, dict) and record.get("entry_id"):
                        records.append(record)
        except (OSError, UnicodeDecodeError) as e:
            console.print(f"[yellow]warning:[/] skipping {path.name}: {e}")
    return records


def _entry_type(record: dict) -> str:
    declared = record.get("entry_type")
    if declared:
        return str(declared)
    prefix = str(record.get("entry_id", "")).split("-", 1)[0]
    return _ID_PREFIX_TYPES.get(prefix, "unknown")


def _formatting(record: dict) -> dict:
    """Score a record's formatting with the current checks, ignoring any stored dict.

    The stored ``formatting`` field is whatever the checks said when the run was
    written, so a table mixing stored and recomputed rows compares metric
    versions as much as models.  ``check_fullwidth_punctuation`` was corrected
    in v0.6.0, and today every committed record happens to agree with a
    recompute — the April runs carry no stored field, and the August runs were
    stamped after the fix.  Recomputing makes that a property of the export
    rather than a coincidence that a single run committed from stale code would
    quietly end.

    :mod:`scripts.analyze_runs` deliberately prefers the stored value and
    flags what it rescored, because it reports on runs as they were recorded.
    This is a cross-run comparison, so uniformity wins instead.
    """
    return formatting_score(str(record.get("source_text", "")), str(record.get("translated_text", "")))


def _model_comparison() -> dict:
    """Per-model formatting fidelity and glossary compliance, for the dashboard.

    ``ratings.json`` already carries Elo and mean judge scores, which need a
    human in the loop.  These two are computed from the committed run files, so
    they cover every model and prompt rather than only the pairs someone has
    judged.

    Glossary compliance is scored against the upstream ``action-translation``
    glossary via :func:`expected_translations` — not the dataset's own
    ``key_terms``, which is empty for every committed entry and would score a
    vacuous 1.0. Records the glossary says nothing about are excluded rather
    than counted as compliant, so ``glossary.scored`` travels with the mean.

    The check is plain containment, so a translation that happens to contain
    the expected characters counts as compliant even when the surrounding text
    is wrong. It reads as an upper bound.

    Formatting is recomputed for every record rather than read from the stored
    field, so each row is scored by the same checks — see :func:`_formatting`.
    """
    records = _run_records()
    glossary = load_glossary()

    grouped: dict[tuple[str, str, str], list[dict]] = {}
    for record in records:
        key = (
            str(record.get("model", "unknown")),
            str(record.get("prompt_template", "unknown")),
            _entry_type(record),
        )
        grouped.setdefault(key, []).append(record)

    rows: list[dict] = []
    for (model, prompt, entry_type), group in sorted(grouped.items()):
        scores = [_formatting(r) for r in group]
        total = len(scores)
        pass_rates = {
            check: round(100.0 * sum(1 for s in scores if s.get(check)) / total, 1)
            for check in _BOOLEAN_CHECKS
        }
        means = {
            check: round(sum(float(s.get(check) or 0.0) for s in scores) / total, 4)
            for check in _SCORE_CHECKS
        }

        compliances = [
            glossary_compliance(str(r.get("translated_text", "")), expected)
            for r in group
            if (expected := expected_translations(str(r.get("source_text", "")), glossary))
        ]
        rows.append(
            {
                "model": model,
                "prompt_template": prompt,
                "entry_type": entry_type,
                "records": total,
                "pass_rates": pass_rates,
                "means": means,
                "glossary": {
                    "scored": len(compliances),
                    "mean": round(sum(compliances) / len(compliances), 4) if compliances else None,
                },
            }
        )

    return {
        "runs": rows,
        "models": sorted({row["model"] for row in rows}),
        "prompts": sorted({row["prompt_template"] for row in rows}),
        "entry_types": sorted({row["entry_type"] for row in rows}),
        "records": len(records),
        "glossary_terms": len(glossary),
    }


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

    # 7. Ratings, recomputed from the committed judgment logs
    ratings = _ratings_export()

    # 8. Model comparison, computed from the committed run files
    models = _model_comparison()

    # Write all export files
    exports = {
        "coverage.json": coverage,
        "domains.json": domains,
        "difficulty.json": difficulty,
        "leaderboard.json": leaderboard,
        "activity.json": activity,
        "samples.json": samples,
        "ratings.json": ratings,
        "models.json": models,
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
        # A dict whose values are themselves collections — ratings.json — says
        # nothing useful as a key count, so name each section and its size.  A
        # section carrying its own "total" reports that instead of its shape.
        sections = []
        for key, value in data.items():
            if isinstance(value, dict) and "total" in value:
                sections.append(f"{key} {value['total']}")
            elif isinstance(value, (list, dict)):
                sections.append(f"{key} {len(value)}")
        return ", ".join(sections) if sections else f"{len(data)} keys"
    return "exported"
