"""Aggregate model-output runs into the Markdown tables used by NOTES.md.

Reads every ``*.jsonl`` run file in ``results/model-outputs/``, groups the
records by (model, prompt template, entry type) and reports:

  1. Cost — entries, tokens, spend and mean latency per run
  2. Formatting — pass rate for each boolean check, mean score for each float
  3. Failure detail — example entry ids behind each failed boolean check
  4. Agreement — pairwise first-line agreement between runs of the same type
  5. Verbosity — records whose translation spans more than one non-empty line

Records written before ``qebench run`` started storing a ``formatting`` field
(the April term runs) are scored on the fly with
:func:`qebench.scoring.formatting.formatting_score` so every run is
comparable; those runs are flagged as retroactively scored in the output.

Run: uv run python scripts/analyze_runs.py [--type paragraphs] [--json out.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path

from qebench.scoring.formatting import formatting_score
from qebench.utils.dataset import RESULTS_DIR

DEFAULT_DIR = RESULTS_DIR / "model-outputs"

# formatting_score() returns three pass/fail checks and two 0-1 scores
BOOLEAN_CHECKS = ("directive_balance", "fence_consistency", "code_block_integrity")
SCORE_CHECKS = ("fullwidth_punctuation", "directive_spacing")
FORMATTING_KEYS = BOOLEAN_CHECKS + SCORE_CHECKS

# April runs predate the entry_type field — recover it from the id prefix
ID_PREFIX_TYPES = {"term": "terms", "sent": "sentences", "para": "paragraphs"}
TYPE_ORDER = ("terms", "sentences", "paragraphs")

DEFAULT_MAX_FAILURES = 5


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Record:
    """One translation record from a run file, with formatting always present."""

    entry_id: str
    source_text: str
    translated_text: str
    model: str
    provider: str
    prompt_template: str
    entry_type: str
    input_tokens: int
    output_tokens: int
    cache_creation_tokens: int
    cache_read_tokens: int
    cost_usd: float
    latency_ms: float
    formatting: dict[str, bool | float]
    formatting_retroactive: bool
    source_file: str


@dataclass
class Run:
    """All records sharing a (model, prompt template, entry type) key."""

    model: str
    prompt_template: str
    entry_type: str
    records: list[Record] = field(default_factory=list)
    files: list[str] = field(default_factory=list)

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.model, self.prompt_template, self.entry_type)

    @property
    def short_label(self) -> str:
        """Model and prompt only — used where entry type is a separate column."""
        return f"{self.model} / {self.prompt_template}"

    @property
    def label(self) -> str:
        return f"{self.model} / {self.prompt_template} / {self.entry_type}"

    @property
    def retroactive(self) -> bool:
        """True when any record in the run needed on-the-fly formatting scores."""
        return any(r.formatting_retroactive for r in self.records)

    @property
    def duplicate_entry_ids(self) -> int:
        """Records beyond the first for an entry id — non-zero means a repeated run.

        Two files can share a (model, prompt, entry type) key when the same
        combination is run twice.  Every record still counts toward cost, but
        the repetition is worth surfacing.
        """
        return len(self.records) - len({r.entry_id for r in self.records})


@dataclass
class LoadResult:
    """Runs recovered from a directory, plus a message per unusable line."""

    runs: list[Run] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    directory_missing: bool = False


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def infer_entry_type(record: dict) -> str:
    """Return the entry type, falling back to the entry id prefix.

    The six April term runs predate the ``entry_type`` field, so ``term-001``
    has to be read back as ``terms``.
    """
    declared = record.get("entry_type")
    if declared:
        return str(declared)
    entry_id = str(record.get("entry_id", ""))
    prefix = entry_id.split("-", 1)[0]
    return ID_PREFIX_TYPES.get(prefix, "unknown")


def resolve_formatting(record: dict) -> tuple[dict[str, bool | float], bool]:
    """Return (formatting scores, computed_retroactively) for a raw record.

    Runs made before the ``formatting`` field existed — and any record whose
    stored dict is incomplete — are scored here so every run is comparable.
    """
    stored = record.get("formatting")
    if isinstance(stored, dict) and all(key in stored for key in FORMATTING_KEYS):
        return {key: stored[key] for key in FORMATTING_KEYS}, False
    scores = formatting_score(str(record.get("source_text", "")), str(record.get("translated_text", "")))
    return scores, True


def parse_record(record: dict, source_file: str) -> Record:
    """Build a :class:`Record` from one raw JSON object."""
    formatting, retroactive = resolve_formatting(record)
    return Record(
        entry_id=str(record.get("entry_id", "")),
        source_text=str(record.get("source_text", "")),
        translated_text=str(record.get("translated_text", "")),
        model=str(record.get("model", "unknown")),
        provider=str(record.get("provider", "unknown")),
        prompt_template=str(record.get("prompt_template", "unknown")),
        entry_type=infer_entry_type(record),
        input_tokens=_as_int(record.get("input_tokens")),
        output_tokens=_as_int(record.get("output_tokens")),
        # Runs made before prompt caching carry neither field, and zero is the
        # truth for them: every prompt token was billed at the full rate.
        cache_creation_tokens=_as_int(record.get("cache_creation_tokens")),
        cache_read_tokens=_as_int(record.get("cache_read_tokens")),
        cost_usd=_as_float(record.get("cost_usd")),
        latency_ms=_as_float(record.get("latency_ms")),
        formatting=formatting,
        formatting_retroactive=retroactive,
        source_file=source_file,
    )


def load_run_file(path: Path) -> tuple[list[Record], list[str]]:
    """Read one JSONL run file, skipping unusable lines with a message each."""
    records: list[Record] = []
    skipped: list[str] = []
    try:
        with open(path, encoding="utf-8") as f:
            for lineno, line in enumerate(f, start=1):
                if not line.strip():
                    continue
                try:
                    raw = json.loads(line)
                except json.JSONDecodeError as exc:
                    skipped.append(f"{path.name}:{lineno}: malformed JSON ({exc.msg})")
                    continue
                if not isinstance(raw, dict):
                    skipped.append(f"{path.name}:{lineno}: expected a JSON object, got {type(raw).__name__}")
                    continue
                if not raw.get("entry_id"):
                    skipped.append(f"{path.name}:{lineno}: record has no entry_id")
                    continue
                records.append(parse_record(raw, path.name))
    except (OSError, UnicodeDecodeError) as exc:
        # One unreadable or non-UTF-8 file must not abort the whole directory.
        skipped.append(f"{path.name}: unreadable, stopped after {len(records)} records ({exc})")
    return records, skipped


def load_directory(directory: Path, *, entry_type: str | None = None) -> LoadResult:
    """Load every ``*.jsonl`` run file in *directory*, grouped into runs.

    Records are grouped by (model, prompt template, entry type), so two files
    covering the same combination merge into one run.  Pass *entry_type* to
    keep only records of that type.
    """
    result = LoadResult()
    if not directory.exists():
        result.skipped.append(f"{directory}: directory not found")
        result.directory_missing = True
        return result

    grouped: dict[tuple[str, str, str], Run] = {}
    for path in sorted(directory.glob("*.jsonl")):
        records, skipped = load_run_file(path)
        result.skipped.extend(skipped)
        for record in records:
            if entry_type and record.entry_type != entry_type:
                continue
            key = (record.model, record.prompt_template, record.entry_type)
            run = grouped.get(key)
            if run is None:
                run = Run(model=key[0], prompt_template=key[1], entry_type=key[2])
                grouped[key] = run
            run.records.append(record)
            if record.source_file not in run.files:
                run.files.append(record.source_file)

    result.runs = sorted(grouped.values(), key=lambda r: (_type_rank(r.entry_type), r.model, r.prompt_template))
    return result


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def cost_rows(runs: list[Run]) -> list[dict]:
    """Entries, tokens, spend and mean latency for each run."""
    rows: list[dict] = []
    for run in runs:
        entries = len(run.records)
        cache_creation_tokens = sum(r.cache_creation_tokens for r in run.records)
        cache_read_tokens = sum(r.cache_read_tokens for r in run.records)
        # Keep "input tokens" meaning the whole prompt, so a cached run stays
        # comparable with the uncached rounds already recorded in NOTES.md.
        input_tokens = (
            sum(r.input_tokens for r in run.records) + cache_creation_tokens + cache_read_tokens
        )
        output_tokens = sum(r.output_tokens for r in run.records)
        cost = sum(r.cost_usd for r in run.records)
        latency = sum(r.latency_ms for r in run.records) / entries if entries else 0.0
        rows.append(
            {
                "run": run.label,
                "model": run.model,
                "prompt_template": run.prompt_template,
                "entry_type": run.entry_type,
                "entries": entries,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_creation_tokens": cache_creation_tokens,
                "cache_read_tokens": cache_read_tokens,
                "total_tokens": input_tokens + output_tokens,
                "cost_usd": round(cost, 6),
                "mean_latency_ms": round(latency, 1),
                "duplicate_entry_ids": run.duplicate_entry_ids,
            }
        )
    return rows


def formatting_rows(runs: list[Run]) -> list[dict]:
    """Pass rate per boolean check and mean score per float check, per run."""
    rows: list[dict] = []
    for run in runs:
        total = len(run.records)
        pass_rates: dict[str, float | None] = {}
        passed_counts: dict[str, int] = {}
        for check in BOOLEAN_CHECKS:
            passed = sum(1 for r in run.records if bool(r.formatting.get(check)))
            passed_counts[check] = passed
            pass_rates[check] = round(100.0 * passed / total, 1) if total else None
        means: dict[str, float | None] = {}
        for check in SCORE_CHECKS:
            values = [_as_float(r.formatting.get(check)) for r in run.records]
            means[check] = round(sum(values) / len(values), 4) if values else None
        rows.append(
            {
                "run": run.label,
                "model": run.model,
                "prompt_template": run.prompt_template,
                "entry_type": run.entry_type,
                "records": total,
                "pass_rates": pass_rates,
                "passed": passed_counts,
                "means": means,
                "retroactive": run.retroactive,
            }
        )
    return rows


def failure_rows(runs: list[Run], *, max_failures: int = DEFAULT_MAX_FAILURES) -> list[dict]:
    """Up to *max_failures* entry ids behind each failed boolean check, per run."""
    rows: list[dict] = []
    for run in runs:
        failures: dict[str, dict] = {}
        for check in BOOLEAN_CHECKS:
            failing = [r.entry_id for r in run.records if not bool(r.formatting.get(check))]
            failures[check] = {"count": len(failing), "entry_ids": failing[:max_failures]}
        rows.append(
            {
                "run": run.label,
                "model": run.model,
                "prompt_template": run.prompt_template,
                "entry_type": run.entry_type,
                "records": len(run.records),
                "total_failures": sum(f["count"] for f in failures.values()),
                "failures": failures,
            }
        )
    return rows


def agreement_rows(runs: list[Run]) -> list[dict]:
    """First-line agreement for every pair of runs sharing an entry type.

    Sentence runs and paragraph runs share no entry ids, so pairs are only
    formed within one entry type.  The rate is over shared ids only.
    """
    rows: list[dict] = []
    by_type: dict[str, list[Run]] = {}
    for run in runs:
        by_type.setdefault(run.entry_type, []).append(run)

    for entry_type in sorted(by_type, key=_type_rank):
        first_lines = {
            run.key: {r.entry_id: first_line(r.translated_text) for r in run.records}
            for run in by_type[entry_type]
        }
        for run_a, run_b in combinations(by_type[entry_type], 2):
            lines_a = first_lines[run_a.key]
            lines_b = first_lines[run_b.key]
            shared = sorted(set(lines_a) & set(lines_b))
            agree = sum(1 for entry_id in shared if lines_a[entry_id] == lines_b[entry_id])
            rows.append(
                {
                    "entry_type": entry_type,
                    "run_a": run_a.short_label,
                    "run_b": run_b.short_label,
                    "shared": len(shared),
                    "agree": agree,
                    "rate": round(agree / len(shared), 4) if shared else None,
                }
            )
    return rows


def verbosity_rows(runs: list[Run], *, max_examples: int = DEFAULT_MAX_FAILURES) -> list[dict]:
    """Records whose translation spans more than one non-empty line, per run.

    April's notes found Haiku emitting commentary instead of translations, so
    a multi-line translation of a single term is a useful warning sign.
    """
    rows: list[dict] = []
    for run in runs:
        multiline = [r.entry_id for r in run.records if count_non_empty_lines(r.translated_text) > 1]
        total = len(run.records)
        rows.append(
            {
                "run": run.label,
                "model": run.model,
                "prompt_template": run.prompt_template,
                "entry_type": run.entry_type,
                "records": total,
                "multiline": len(multiline),
                "pct": round(100.0 * len(multiline) / total, 1) if total else None,
                "entry_ids": multiline[:max_examples],
            }
        )
    return rows


def aggregate(runs: list[Run], *, max_failures: int = DEFAULT_MAX_FAILURES) -> dict:
    """Build every aggregate table from the loaded runs."""
    return {
        "runs": [
            {
                "run": run.label,
                "model": run.model,
                "prompt_template": run.prompt_template,
                "entry_type": run.entry_type,
                "records": len(run.records),
                "files": run.files,
                "retroactive": run.retroactive,
                "duplicate_entry_ids": run.duplicate_entry_ids,
            }
            for run in runs
        ],
        "cost": cost_rows(runs),
        "formatting": formatting_rows(runs),
        "failures": failure_rows(runs, max_failures=max_failures),
        "agreement": agreement_rows(runs),
        "verbosity": verbosity_rows(runs, max_examples=max_failures),
        "retroactive_runs": [run.label for run in runs if run.retroactive],
    }


def analyse(
    directory: Path,
    *,
    entry_type: str | None = None,
    max_failures: int = DEFAULT_MAX_FAILURES,
) -> dict:
    """Load *directory* and return every aggregate, plus skipped-line messages."""
    loaded = load_directory(directory, entry_type=entry_type)
    aggregates = aggregate(loaded.runs, max_failures=max_failures)
    aggregates["directory"] = str(directory)
    aggregates["entry_type_filter"] = entry_type
    aggregates["skipped"] = loaded.skipped
    aggregates["directory_missing"] = loaded.directory_missing
    return aggregates


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def render_markdown(aggregates: dict) -> str:
    """Render the aggregates as Markdown sections ready to paste into NOTES.md."""
    parts: list[str] = ["# Run Analysis", ""]

    directory = aggregates.get("directory")
    entry_filter = aggregates.get("entry_type_filter")
    scope = f"`{directory}`" if directory else "the run directory"
    if entry_filter:
        scope += f" (entry type: {entry_filter})"
    parts.append(f"Source: {scope}")
    parts.append("")

    skipped = aggregates.get("skipped") or []

    if not aggregates["runs"]:
        parts.append("No run records found.")
        parts.append("")
        # Still say why — otherwise a bad --dir or a corrupt file looks like an
        # empty directory in the one artefact that gets pasted into NOTES.md.
        parts.extend(_render_skipped(skipped))
        return "\n".join(parts)

    parts.extend(_render_cost(aggregates["cost"]))
    parts.extend(_render_formatting(aggregates["formatting"], aggregates["retroactive_runs"]))
    parts.extend(_render_failures(aggregates["failures"]))
    parts.extend(_render_agreement(aggregates["agreement"]))
    parts.extend(_render_verbosity(aggregates["verbosity"]))

    parts.extend(_render_skipped(skipped))

    return "\n".join(parts)


def _render_skipped(skipped: list[str]) -> list[str]:
    """Render the skipped-line diagnostics, or nothing when there are none."""
    if not skipped:
        return []
    lines = ["## Skipped Lines", ""]
    lines.extend(f"- {message}" for message in skipped)
    lines.append("")
    return lines


def _render_cost(rows: list[dict]) -> list[str]:
    cached = any(row.get("cache_read_tokens") or row.get("cache_creation_tokens") for row in rows)
    headers = ["Run", "Type", "Entries", "Input tok", "Output tok", "Cost", "Mean latency"]
    if cached:
        headers.insert(5, "Cached tok")
    body = []
    for row in rows:
        cells = [
            f"{row['model']} / {row['prompt_template']}",
            row["entry_type"],
            f"{row['entries']:,}",
            f"{row['input_tokens']:,}",
            f"{row['output_tokens']:,}",
            f"${row['cost_usd']:.4f}",
            f"{row['mean_latency_ms']:,.0f}ms",
        ]
        if cached:
            served = row.get("cache_read_tokens") or 0
            cells.insert(5, f"{served:,}" if served else "—")
        body.append(cells)
    total_cost = sum(row["cost_usd"] for row in rows)
    total_entries = sum(row["entries"] for row in rows)
    lines = ["## Runs", ""]
    lines.extend(_table(headers, body))
    lines.append("")
    lines.append(f"Total: {total_entries:,} translations across {len(rows)} runs, ${total_cost:.4f} combined cost.")
    lines.append("")
    repeated = [row for row in rows if row["duplicate_entry_ids"]]
    if repeated:
        lines.append(
            "Repeated entry ids (the same model, prompt and type was run more than once): "
            + ", ".join(f"`{row['run']}` ({row['duplicate_entry_ids']})" for row in repeated)
        )
        lines.append("")
    return lines


def _render_formatting(rows: list[dict], retroactive_runs: list[str]) -> list[str]:
    headers = [
        "Run",
        "Type",
        "N",
        "Directive balance",
        "Fence consistency",
        "Code integrity",
        "Full-width punct",
        "Directive spacing",
    ]
    body = [
        [
            f"{row['model']} / {row['prompt_template']}",
            row["entry_type"],
            str(row["records"]),
            _pct(row["pass_rates"]["directive_balance"]),
            _pct(row["pass_rates"]["fence_consistency"]),
            _pct(row["pass_rates"]["code_block_integrity"]),
            _score(row["means"]["fullwidth_punctuation"]),
            _score(row["means"]["directive_spacing"]),
        ]
        for row in rows
    ]
    lines = ["## Formatting", ""]
    lines.append("Pass rate for the three boolean checks, mean score for the two 0-1 checks.")
    lines.append("")
    lines.extend(_table(headers, body))
    lines.append("")
    if retroactive_runs:
        lines.append(
            "Scored retroactively (records predate the `formatting` field): "
            + ", ".join(f"`{label}`" for label in retroactive_runs)
        )
        lines.append("")
    return lines


def _render_failures(rows: list[dict]) -> list[str]:
    lines = ["## Formatting Failures", ""]
    failing = [row for row in rows if row["total_failures"]]
    if not failing:
        lines.append("No boolean formatting check failed in any run.")
        lines.append("")
        return lines

    headers = ["Run", "Type", "Check", "Failures", "Example entry ids"]
    body: list[list[str]] = []
    for row in failing:
        for check, detail in row["failures"].items():
            if not detail["count"]:
                continue
            body.append(
                [
                    f"{row['model']} / {row['prompt_template']}",
                    row["entry_type"],
                    check,
                    f"{detail['count']}/{row['records']}",
                    ", ".join(f"`{entry_id}`" for entry_id in detail["entry_ids"]) or "—",
                ]
            )
    lines.extend(_table(headers, body))
    lines.append("")
    return lines


def _render_agreement(rows: list[dict]) -> list[str]:
    lines = ["## Agreement", ""]
    if not rows:
        lines.append("Only one run per entry type — no pairs to compare.")
        lines.append("")
        return lines

    lines.append("Pairwise first-line agreement, over entry ids the two runs share.")
    lines.append("")
    headers = ["Type", "Pair", "Agreement"]
    body = [
        [
            row["entry_type"],
            f"{row['run_a']} vs {row['run_b']}",
            f"{row['agree']}/{row['shared']} ({row['rate']:.0%})" if row["shared"] else "no shared entries",
        ]
        for row in rows
    ]
    lines.extend(_table(headers, body))
    lines.append("")
    return lines


def _render_verbosity(rows: list[dict]) -> list[str]:
    lines = ["## Verbosity", ""]
    lines.append("Records whose translation has more than one non-empty line — often commentary, not translation.")
    lines.append("")
    headers = ["Run", "Type", "Multi-line", "Share", "Example entry ids"]
    body = [
        [
            f"{row['model']} / {row['prompt_template']}",
            row["entry_type"],
            f"{row['multiline']}/{row['records']}",
            _pct(row["pct"]),
            ", ".join(f"`{entry_id}`" for entry_id in row["entry_ids"]) or "—",
        ]
        for row in rows
    ]
    lines.extend(_table(headers, body))
    lines.append("")
    return lines


def _table(headers: list[str], rows: list[list[str]]) -> list[str]:
    """Render a Markdown table as a list of lines."""
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return lines


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def first_line(text: str) -> str:
    """Return the first non-empty line, normalised for whitespace."""
    for line in text.splitlines():
        normalised = " ".join(line.split())
        if normalised:
            return normalised
    return ""


def count_non_empty_lines(text: str) -> int:
    """Count lines that hold something other than whitespace."""
    return sum(1 for line in text.splitlines() if line.strip())


def _type_rank(entry_type: str) -> tuple[int, str]:
    """Sort key putting terms, sentences, paragraphs first, then the rest."""
    if entry_type in TYPE_ORDER:
        return (TYPE_ORDER.index(entry_type), "")
    return (len(TYPE_ORDER), entry_type)


def _as_int(value: object) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def _as_float(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value:.1f}%"


def _score(value: float | None) -> str:
    return "—" if value is None else f"{value:.3f}"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    """Parse arguments, print the Markdown report and optionally dump JSON."""
    parser = argparse.ArgumentParser(description="Aggregate qebench model-output runs into Markdown tables.")
    parser.add_argument(
        "--dir",
        type=Path,
        default=DEFAULT_DIR,
        help="Directory of *.jsonl run files (default: results/model-outputs).",
    )
    parser.add_argument(
        "--type",
        dest="entry_type",
        default=None,
        help="Restrict to one entry type: terms, sentences, paragraphs.",
    )
    parser.add_argument("--json", dest="json_path", type=Path, default=None, help="Also dump the aggregates as JSON.")
    parser.add_argument(
        "--max-failures",
        type=int,
        default=DEFAULT_MAX_FAILURES,
        help=f"Example entry ids to list per failed check (default: {DEFAULT_MAX_FAILURES}).",
    )
    args = parser.parse_args(argv)

    aggregates = analyse(args.dir, entry_type=args.entry_type, max_failures=args.max_failures)
    for message in aggregates["skipped"]:
        print(f"warning: {message}", file=sys.stderr)

    print(render_markdown(aggregates))

    if aggregates["directory_missing"]:
        # A mistyped --dir otherwise produces an empty report and exit 0, which
        # in CI is indistinguishable from a run that genuinely found nothing.
        print(f"error: {args.dir}: directory not found", file=sys.stderr)
        return 2

    if args.json_path:
        args.json_path.parent.mkdir(parents=True, exist_ok=True)
        with open(args.json_path, "w", encoding="utf-8") as f:
            json.dump(aggregates, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print(f"Wrote {args.json_path}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
