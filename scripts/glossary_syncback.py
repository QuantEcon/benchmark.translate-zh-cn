#!/usr/bin/env python3
"""Propose glossary changes from benchmark evidence (benchmark → action-translation).

Closes the feedback loop described in REVIEW.md §8: the benchmark is seeded
*from* ``action-translation``'s glossary, and this script sends findings back.

Three sources of evidence are compared against the upstream glossary loaded by
:func:`qebench.utils.dataset.load_glossary` — the benchmark term dataset, human
attempts in ``results/translations/``, and LLM outputs in
``results/model-outputs/`` — producing three categories of *candidate* change:

- ``CORRECTIONS``    glossary terms where distinct annotators agree on a different translation
- ``ADDITIONS``      human-verified benchmark terms that are missing from the glossary
- ``NEEDS_CONTEXT``  glossary terms the models fail to reproduce in most runs

The script is read-only with respect to the glossary.  It never opens a pull
request, never pushes, and never edits ``glossary/zh-cn.json``; every candidate
is written to ``results/glossary-syncback/`` for a human to review first.

Run: uv run python scripts/glossary_syncback.py [--min-annotators 2]
"""

from __future__ import annotations

import argparse
import json
import string
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from rich.table import Table

from qebench.models import Term
from qebench.utils.dataset import load_glossary, load_terms
from qebench.utils.display import console

_REPO_ROOT = Path(__file__).resolve().parents[1]
TRANSLATIONS_DIR = _REPO_ROOT / "results" / "translations"
MODEL_OUTPUTS_DIR = _REPO_ROOT / "results" / "model-outputs"
OUTPUT_DIR = _REPO_ROOT / "results" / "glossary-syncback"

DEFAULT_MIN_ANNOTATORS = 2
COMPLIANCE_THRESHOLD = 0.5

# ASCII punctuation plus its full-width variants (U+FF01–U+FF5E mirror U+0021–U+007E).
_PUNCTUATION = frozenset(string.punctuation) | frozenset(chr(ord(ch) + 0xFEE0) for ch in string.punctuation)


# --- normalisation -----------------------------------------------------------


def normalise_zh(text: str) -> str:
    """Normalise a Chinese translation for comparison.

    Strips whitespace along with ASCII, full-width, and CJK punctuation, so
    that ``"价值函数。"``, ``"价值函数"`` and ``" 价值 函数 "`` all compare equal.
    Every translation comparison in this module goes through this helper —
    never compare raw strings.
    """
    return "".join(
        ch
        for ch in text
        if not ch.isspace() and ch not in _PUNCTUATION and not unicodedata.category(ch).startswith(("P", "C", "Z"))
    )


def normalise_en(text: str) -> str:
    """Normalise an English term for matching: case-folded, whitespace-collapsed."""
    return " ".join(text.split()).casefold()


def first_line(text: str) -> str:
    """Return the first non-empty line of a model output, stripped.

    Some models wrap the translation in commentary; the first non-empty line
    is the translation itself, which is what exact-match logic compares.
    """
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


# --- evidence records --------------------------------------------------------


@dataclass(frozen=True)
class HumanAttempt:
    """One human translation attempt from ``results/translations/<username>.jsonl``."""

    entry_id: str
    username: str
    attempt: str
    reference: str = ""
    confidence: int | None = None


@dataclass(frozen=True)
class ModelOutput:
    """One LLM translation from ``results/model-outputs/<run>.jsonl``."""

    entry_id: str
    translated_text: str
    model: str = ""
    prompt_template: str = ""
    entry_type: str = ""

    @property
    def run_label(self) -> str:
        """Short ``model/prompt`` label used to attribute an output in reports."""
        return f"{self.model}/{self.prompt_template}" if self.prompt_template else self.model


def _iter_jsonl(path: Path) -> Iterator[dict]:
    """Yield dict records from a JSONL file, skipping malformed lines with a warning."""
    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as e:
                console.print(f"[yellow]warning:[/] skipping malformed line {lineno} in {path.name}: {e}")
                continue
            if isinstance(record, dict):
                yield record


def load_human_attempts(directory: Path | None = None) -> list[HumanAttempt]:
    """Load every human attempt from ``results/translations/*.jsonl``.

    One file per annotator — the username is the file stem.
    """
    directory = TRANSLATIONS_DIR if directory is None else directory
    attempts: list[HumanAttempt] = []
    if not directory.exists():
        return attempts

    for path in sorted(directory.glob("*.jsonl")):
        username = path.stem
        for record in _iter_jsonl(path):
            entry_id = record.get("entry_id", "")
            attempt = record.get("attempt", "")
            if not entry_id or not attempt:
                continue
            confidence = record.get("confidence")
            attempts.append(
                HumanAttempt(
                    entry_id=entry_id,
                    username=username,
                    attempt=attempt,
                    reference=record.get("reference", ""),
                    confidence=confidence if isinstance(confidence, int) else None,
                )
            )
    return attempts


def load_model_outputs(directory: Path | None = None) -> list[ModelOutput]:
    """Load every LLM translation from ``results/model-outputs/*.jsonl``."""
    directory = MODEL_OUTPUTS_DIR if directory is None else directory
    outputs: list[ModelOutput] = []
    if not directory.exists():
        return outputs

    for path in sorted(directory.glob("*.jsonl")):
        for record in _iter_jsonl(path):
            entry_id = record.get("entry_id", "")
            translated = record.get("translated_text", "")
            if not entry_id or not translated:
                continue
            outputs.append(
                ModelOutput(
                    entry_id=entry_id,
                    translated_text=translated,
                    model=record.get("model", ""),
                    prompt_template=record.get("prompt_template", ""),
                    entry_type=record.get("entry_type", ""),
                )
            )
    return outputs


# --- glossary indexing -------------------------------------------------------


def glossary_zh(entry: dict) -> str:
    """Target-language translation of a glossary entry."""
    return entry.get("zh-cn") or entry.get("zh") or ""


def build_glossary_index(glossary: list[dict]) -> dict[str, dict]:
    """Index glossary entries by normalised English term.

    Matching is case-insensitive and whitespace-normalised on both sides.  The
    first entry wins when the upstream glossary contains duplicate headwords.
    """
    index: dict[str, dict] = {}
    for entry in glossary:
        en = entry.get("en", "")
        if not en or not glossary_zh(entry):
            continue
        index.setdefault(normalise_en(en), entry)
    return index


def _attempts_by_entry(attempts: list[HumanAttempt]) -> dict[str, list[HumanAttempt]]:
    """Group human attempts by the benchmark entry they translate."""
    grouped: dict[str, list[HumanAttempt]] = defaultdict(list)
    for attempt in attempts:
        grouped[attempt.entry_id].append(attempt)
    return grouped


def _preferred_form(attempts: list[HumanAttempt]) -> str:
    """Pick the most frequent raw spelling among attempts that normalise alike."""
    counts = Counter(attempt.attempt.strip() for attempt in attempts)
    return counts.most_common(1)[0][0]


def _confidence_map(attempts: list[HumanAttempt]) -> dict[str, int | None]:
    """Map each annotator to the confidence on their supporting attempt."""
    return {attempt.username: attempt.confidence for attempt in attempts}


# --- candidate detection -----------------------------------------------------


def find_corrections(
    terms: list[Term],
    glossary_index: dict[str, dict],
    attempts: list[HumanAttempt],
    *,
    min_annotators: int = DEFAULT_MIN_ANNOTATORS,
) -> list[dict]:
    """Glossary terms where the human evidence disagrees with the glossary.

    A candidate requires *min_annotators* DISTINCT usernames (not attempts)
    proposing the same normalised translation, and that translation must
    differ from the glossary's.  Attempts that match the glossary are evidence
    FOR it and are ignored here.
    """
    by_entry = _attempts_by_entry(attempts)
    candidates: list[dict] = []

    for term in terms:
        entry = glossary_index.get(normalise_en(term.en))
        if entry is None:
            continue
        current = normalise_zh(glossary_zh(entry))

        variants: dict[str, list[HumanAttempt]] = defaultdict(list)
        for attempt in by_entry.get(term.id, []):
            key = normalise_zh(attempt.attempt)
            if not key or key == current:
                continue
            variants[key].append(attempt)

        for supporting in variants.values():
            annotators = sorted({attempt.username for attempt in supporting})
            if len(annotators) < min_annotators:
                continue
            candidates.append({
                "term_id": term.id,
                "en": term.en,
                "domain": term.domain,
                "glossary_zh": glossary_zh(entry),
                "benchmark_zh": term.zh,
                "proposed_zh": _preferred_form(supporting),
                "annotators": annotators,
                "confidences": _confidence_map(supporting),
                "attempts": len(supporting),
            })

    candidates.sort(key=lambda c: (-len(c["annotators"]), -c["attempts"], c["en"]))
    return candidates


def find_additions(
    terms: list[Term],
    glossary_index: dict[str, dict],
    attempts: list[HumanAttempt],
) -> list[dict]:
    """Benchmark terms absent from the glossary that humans have verified.

    Evidence is the benchmark reference translation plus at least one human
    attempt that matches it.
    """
    by_entry = _attempts_by_entry(attempts)
    candidates: list[dict] = []

    for term in terms:
        if normalise_en(term.en) in glossary_index:
            continue
        reference = normalise_zh(term.zh)
        if not reference:
            continue

        term_attempts = by_entry.get(term.id, [])
        matching = [attempt for attempt in term_attempts if normalise_zh(attempt.attempt) == reference]
        if not matching:
            continue

        annotators = sorted({attempt.username for attempt in matching})
        candidates.append({
            "term_id": term.id,
            "en": term.en,
            "domain": term.domain,
            "proposed_zh": term.zh,
            "alternatives": list(term.alternatives),
            "evidence": {
                "annotators": annotators,
                "confidences": _confidence_map(matching),
                "matching_attempts": len(matching),
                "total_attempts": len(term_attempts),
            },
        })

    candidates.sort(key=lambda c: (-len(c["evidence"]["annotators"]), c["en"]))
    return candidates


def find_needs_context(
    terms: list[Term],
    glossary_index: dict[str, dict],
    outputs: list[ModelOutput],
    *,
    threshold: float = COMPLIANCE_THRESHOLD,
) -> list[dict]:
    """Glossary terms the models do not reliably reproduce.

    Compliance is substring containment of the glossary translation anywhere in
    the model output (normalised on both sides), so a correct term buried in
    commentary still counts.  Terms complying in fewer than *threshold* of
    their runs need stronger context or enforcement upstream; the worst
    offenders rank first.
    """
    by_entry: dict[str, list[ModelOutput]] = defaultdict(list)
    for output in outputs:
        by_entry[output.entry_id].append(output)

    candidates: list[dict] = []
    for term in terms:
        entry = glossary_index.get(normalise_en(term.en))
        if entry is None:
            continue
        runs = by_entry.get(term.id, [])
        expected = normalise_zh(glossary_zh(entry))
        if not runs or not expected:
            continue

        compliant = 0
        # Keyed on the NORMALISED alternative so that "科布-道格拉斯" and
        # "科布-道格拉斯。" are one row, not two; the raw spellings are counted
        # within each group so the most frequent one can be reported.
        produced: dict[str, Counter[str]] = defaultdict(Counter)
        sources: dict[str, set[str]] = defaultdict(set)
        for run in runs:
            if expected in normalise_zh(run.translated_text):
                compliant += 1
                continue
            alternative = first_line(run.translated_text)
            key = normalise_zh(alternative)
            produced[key][alternative] += 1
            sources[key].add(run.run_label)

        compliance = compliant / len(runs)
        if compliance >= threshold:
            continue

        candidates.append({
            "term_id": term.id,
            "en": term.en,
            "domain": term.domain,
            "glossary_zh": glossary_zh(entry),
            "benchmark_zh": term.zh,
            "compliant_runs": compliant,
            "total_runs": len(runs),
            "compliance": round(compliance, 4),
            "models_produced": [
                {
                    "zh": spellings.most_common(1)[0][0],
                    "runs": sum(spellings.values()),
                    "sources": sorted(sources[alt_key]),
                }
                for alt_key, spellings in sorted(produced.items(), key=lambda kv: -sum(kv[1].values()))
            ],
        })

    candidates.sort(key=lambda c: (c["compliance"], -c["total_runs"], c["en"]))
    return candidates


# --- reporting ---------------------------------------------------------------


def build_report(
    glossary: list[dict],
    terms: list[Term],
    attempts: list[HumanAttempt],
    outputs: list[ModelOutput],
    *,
    min_annotators: int = DEFAULT_MIN_ANNOTATORS,
) -> dict:
    """Assemble the full candidate report from all four evidence sources."""
    index = build_glossary_index(glossary)
    corrections = find_corrections(terms, index, attempts, min_annotators=min_annotators)
    additions = find_additions(terms, index, attempts)
    needs_context = find_needs_context(terms, index, outputs)

    return {
        "generated": datetime.now(UTC).isoformat(),
        "min_annotators": min_annotators,
        "counts": {
            "glossary_terms": len(index),
            "benchmark_terms": len(terms),
            "human_attempts": len(attempts),
            "model_outputs": len(outputs),
            "corrections": len(corrections),
            "additions": len(additions),
            "needs_context": len(needs_context),
        },
        "corrections": corrections,
        "additions": additions,
        "needs_context": needs_context,
    }


def _format_confidences(confidences: dict[str, int | None]) -> str:
    """Render an annotator → confidence map as ``user:4, other:5``."""
    parts = [f"{user}:{value}" for user, value in sorted(confidences.items()) if value is not None]
    return ", ".join(parts) if parts else "—"


def render_markdown(report: dict) -> str:
    """Render the candidate report as Markdown for human review."""
    counts = report["counts"]
    lines = [
        "# Glossary sync-back candidates",
        "",
        f"Generated: {report['generated']}",
        "",
        f"Evidence: {counts['benchmark_terms']} benchmark terms, {counts['glossary_terms']} glossary terms, "
        f"{counts['human_attempts']} human attempts, {counts['model_outputs']} model outputs.",
        "",
        "**Candidates only.** Nothing here has been applied to the glossary. Review every row before opening a "
        "pull request against `QuantEcon/action-translation`.",
        "",
        "## Corrections",
        "",
    ]

    if not report["corrections"]:
        lines += ["_No candidates._", ""]
    else:
        lines += [
            f"{len(report['corrections'])} glossary terms where at least {report['min_annotators']} distinct "
            "annotators agree on a translation that differs from the glossary.",
            "",
            "| Term | Glossary | Proposed | Annotators | Confidence |",
            "|---|---|---|---|---|",
        ]
        for candidate in report["corrections"]:
            lines.append(
                f"| {candidate['en']} (`{candidate['term_id']}`) | {candidate['glossary_zh']} | "
                f"{candidate['proposed_zh']} | {', '.join(candidate['annotators'])} | "
                f"{_format_confidences(candidate['confidences'])} |"
            )
        lines.append("")

    lines += ["## Additions", ""]
    if not report["additions"]:
        lines += ["_No candidates._", ""]
    else:
        lines += [
            f"{len(report['additions'])} benchmark terms missing from the glossary with at least one human "
            "attempt matching the benchmark reference.",
            "",
            "| Term | Proposed | Domain | Evidence |",
            "|---|---|---|---|",
        ]
        for candidate in report["additions"]:
            evidence = candidate["evidence"]
            support = (
                f"{len(evidence['annotators'])} annotator(s) ({', '.join(evidence['annotators'])}), "
                f"{evidence['matching_attempts']}/{evidence['total_attempts']} attempts match"
            )
            lines.append(
                f"| {candidate['en']} (`{candidate['term_id']}`) | {candidate['proposed_zh']} | "
                f"{candidate['domain']} | {support} |"
            )
        lines.append("")

    lines += ["## Needs context", ""]
    if not report["needs_context"]:
        lines += ["_No candidates._", ""]
    else:
        lines += [
            f"{len(report['needs_context'])} glossary terms that the models reproduce in fewer than half of their "
            "runs — these need stronger glossary context or enforcement. Worst first.",
            "",
            "| Term | Glossary | Compliance | Models produced instead |",
            "|---|---|---|---|",
        ]
        for candidate in report["needs_context"]:
            produced = ", ".join(
                f"{item['zh']} ×{item['runs']}" for item in candidate["models_produced"][:3]
            ) or "—"
            lines.append(
                f"| {candidate['en']} (`{candidate['term_id']}`) | {candidate['glossary_zh']} | "
                f"{candidate['compliant_runs']}/{candidate['total_runs']} "
                f"({candidate['compliance']:.0%}) | {produced} |"
            )
        lines.append("")

    return "\n".join(lines) + "\n"


def render_summary(report: dict) -> None:
    """Print a summary table of the candidate counts to the console."""
    counts = report["counts"]
    table = Table(title="Glossary Sync-Back Candidates", border_style="dim")
    table.add_column("Category", style="cyan")
    table.add_column("Candidates", justify="right", style="bold yellow")
    table.add_column("Criterion", style="dim")
    table.add_row(
        "CORRECTIONS",
        str(counts["corrections"]),
        f"≥{report['min_annotators']} annotators agree against the glossary",
    )
    table.add_row("ADDITIONS", str(counts["additions"]), "human-verified terms missing from the glossary")
    table.add_row(
        "NEEDS_CONTEXT",
        str(counts["needs_context"]),
        f"glossary term reproduced in <{COMPLIANCE_THRESHOLD:.0%} of model runs",
    )

    console.print()
    console.print(table)
    console.print(
        f"  [dim]evidence: {counts['benchmark_terms']} benchmark terms, {counts['glossary_terms']} glossary terms, "
        f"{counts['human_attempts']} human attempts, {counts['model_outputs']} model outputs[/dim]"
    )

    worst = report["needs_context"][:5]
    if worst:
        detail = Table(title="Weakest Glossary Compliance", border_style="dim")
        detail.add_column("Term", style="cyan")
        detail.add_column("Glossary", style="green")
        detail.add_column("Runs", justify="right")
        detail.add_column("Models produced instead", style="magenta")
        for candidate in worst:
            produced = ", ".join(f"{item['zh']} ×{item['runs']}" for item in candidate["models_produced"][:2])
            detail.add_row(
                candidate["en"],
                candidate["glossary_zh"],
                f"{candidate['compliant_runs']}/{candidate['total_runs']}",
                produced or "—",
            )
        console.print()
        console.print(detail)


def write_reports(report: dict, output_dir: Path) -> tuple[Path, Path]:
    """Write the JSON and Markdown reports, creating *output_dir* if needed."""
    output_dir.mkdir(parents=True, exist_ok=True)
    gitkeep = output_dir / ".gitkeep"
    if not gitkeep.exists():
        gitkeep.touch()

    json_path = output_dir / "glossary-syncback.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        f.write("\n")

    md_path = output_dir / "glossary-syncback.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(render_markdown(report))

    return json_path, md_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Propose glossary changes from benchmark evidence. Emits candidates only — "
            "it never edits the glossary, pushes, or opens a pull request."
        )
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUT_DIR,
        help="Directory for the JSON and Markdown reports (default: results/glossary-syncback).",
    )
    parser.add_argument(
        "--min-annotators",
        type=int,
        default=DEFAULT_MIN_ANNOTATORS,
        help="Distinct annotators that must agree before a correction is proposed (default: %(default)s).",
    )
    args = parser.parse_args()

    if args.min_annotators < 1:
        parser.error("--min-annotators must be at least 1")

    glossary = load_glossary()
    if not glossary:
        console.print("[yellow]warning:[/] glossary is empty — check glossary_path in config.yaml")

    report = build_report(
        glossary,
        load_terms(),
        load_human_attempts(),
        load_model_outputs(),
        min_annotators=args.min_annotators,
    )
    json_path, md_path = write_reports(report, args.output_dir)

    render_summary(report)
    console.print()
    console.print(f"  [dim]{json_path}[/dim]")
    console.print(f"  [dim]{md_path}[/dim]")
    console.print()


if __name__ == "__main__":
    main()
