"""translate command — Interactive translation data collection.

The main engagement loop: shows English text, collects the user's Chinese
translation and a confidence rating, then reveals the reference with a
character-similarity score.  When the translation differs from the reference,
the user is prompted for the reason (formal/informal register, regional
preference, context, etc.).  This captures both the *variation* and the
*why* behind it — valuable data for improving our translator.

Entries are served by consensus need rather than uniformly: an entry that
exactly one other annotator has attempted is one attempt away from being a
consensus entry, so it is offered first.  Pass ``--uniform`` to opt out.
"""

from __future__ import annotations

import json
import random
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime

import questionary
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

from qebench import __version__
from qebench.models import Difficulty, Paragraph, Sentence, Term
from qebench.scoring.xp import award_xp, load_xp
from qebench.utils.dataset import DATA_DIR, load_all
from qebench.utils.display import console
from qebench.utils.github import get_github_username

RESULTS_DIR = DATA_DIR.parent / "results" / "translations"

# Similarity threshold below which we ask for a reason
DIFF_THRESHOLD = 0.85

# Sampling weights, keyed on how many *other* annotators have already
# attempted an entry.  One existing annotator is the sweet spot: a second
# attempt turns the entry into a consensus entry.  The gap between the first
# two is sized so that a session splits roughly evenly between building
# consensus and extending first-pass coverage, and it self-corrects: as the
# needs-a-second pool drains, unseen entries take over on their own.
WEIGHT_NEEDS_SECOND = 12.0
WEIGHT_UNSEEN = 3.0
WEIGHT_WELL_COVERED = 0.5

_NO_ANNOTATORS: frozenset[str] = frozenset()

CONFIDENCE_CHOICES = [
    questionary.Choice("1 — Guessing", value=1, shortcut_key="1"),
    questionary.Choice("2 — Uncertain", value=2, shortcut_key="2"),
    questionary.Choice("3 — Reasonable", value=3, shortcut_key="3"),
    questionary.Choice("4 — Confident", value=4, shortcut_key="4"),
    questionary.Choice("5 — Very confident", value=5, shortcut_key="5"),
]

DIFF_REASON_CHOICES = [
    questionary.Choice("Formal/written register (书面语)", value="formal-register", shortcut_key="1"),
    questionary.Choice("Informal/spoken register (口语)", value="informal-register", shortcut_key="2"),
    questionary.Choice("Regional preference", value="regional", shortcut_key="3"),
    questionary.Choice("Contextual — depends on usage", value="contextual", shortcut_key="4"),
    questionary.Choice("Abbreviation or shorthand", value="abbreviation", shortcut_key="5"),
    questionary.Choice("Alternative technical term", value="alt-technical", shortcut_key="6"),
    questionary.Choice("Other (explain in notes)", value="other", shortcut_key="7"),
]


def _char_overlap(attempt: str, reference: str) -> float:
    """Character-level Jaccard similarity between two Chinese strings.

    Strips whitespace and punctuation for comparison.
    Returns a value between 0.0 and 1.0.
    """
    strip_chars = set(" \t\n，。、；：！？（）""''《》【】")
    a_chars = set(attempt) - strip_chars
    r_chars = set(reference) - strip_chars
    if not a_chars and not r_chars:
        return 1.0
    if not a_chars or not r_chars:
        return 0.0
    intersection = a_chars & r_chars
    union = a_chars | r_chars
    return len(intersection) / len(union)


def _annotator_coverage() -> dict[str, set[str]]:
    """Map each attempted entry id to the set of usernames who attempted it.

    Reads every ``results/translations/*.jsonl`` file, taking the username
    from the file stem and the entry id from each record.  A missing
    directory yields an empty mapping, and a malformed line — or a whole
    unreadable file — is reported and skipped rather than aborting the
    session.  Contributors hand-edit these files, so one saved in the wrong
    encoding must not cost every other annotator their coverage.
    """
    coverage: dict[str, set[str]] = {}
    if not RESULTS_DIR.exists():
        return coverage

    for path in sorted(RESULTS_DIR.glob("*.jsonl")):
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
                        continue
                    entry_id = record.get("entry_id")
                    if not isinstance(entry_id, str) or not entry_id:
                        continue
                    coverage.setdefault(entry_id, set()).add(username)
        except (OSError, UnicodeDecodeError) as e:
            # Raised by open() and, for a decode error, by the iterator —
            # so it must be caught around the loop, not around json.loads.
            console.print(
                f"[yellow]warning:[/] {path.name} unreadable after {lineno} line(s), "
                f"skipping the rest: {e}"
            )
            continue

    return coverage


def _entry_weight(
    entry_id: str,
    coverage: Mapping[str, set[str]],
    username: str | None,
) -> float:
    """Sampling weight for one entry, given who has already attempted it.

    The current user's own attempts never count towards coverage — only a
    *different* annotator moves an entry towards consensus.  An entry this
    user has already attempted can never gain from a repeat, so it drops to
    the lowest weight regardless of who else has seen it.  That case is
    normally filtered out before weighting, but it is reachable through the
    empty-pool fallback in :func:`_pick_entries`.
    """
    annotators = coverage.get(entry_id, _NO_ANNOTATORS)
    if username is not None and username in annotators:
        return WEIGHT_WELL_COVERED

    others = {name for name in annotators if name != username}
    if len(others) == 1:
        return WEIGHT_NEEDS_SECOND
    if not others:
        return WEIGHT_UNSEEN
    return WEIGHT_WELL_COVERED


def _needs_second_annotator(
    entry_id: str,
    coverage: Mapping[str, set[str]],
    username: str | None,
) -> bool:
    """True when *this user's* attempt would make the entry a consensus entry.

    That needs exactly one existing annotator, and it must not be this user —
    an entry they have already attempted has its second annotator (them) and
    cannot be pushed to consensus by attempting it again.
    """
    annotators = coverage.get(entry_id, _NO_ANNOTATORS)
    if username is not None and username in annotators:
        return False
    return len(annotators) == 1


def _weighted_sample(
    pool: Sequence[Term | Sentence | Paragraph],
    weights: Sequence[float],
    count: int,
) -> list[Term | Sentence | Paragraph]:
    """Draw *count* entries without replacement, proportional to *weights*.

    Uses the Efraimidis–Spirakis exponential-key trick: each candidate gets
    the key ``random() ** (1 / weight)`` and the highest keys win.  Unlike
    ``random.choices`` this never returns the same entry twice.
    """
    keyed = [
        (random.random() ** (1.0 / max(weight, 1e-9)), i)
        for i, weight in enumerate(weights)
    ]
    keyed.sort(key=lambda pair: pair[0], reverse=True)
    return [pool[i] for _, i in keyed[:count]]


def _pick_entries(
    terms: list[Term],
    sentences: list[Sentence],
    paragraphs: list[Paragraph],
    domain: str | None,
    difficulty: str | None,
    count: int,
    *,
    username: str | None = None,
    coverage: Mapping[str, set[str]] | None = None,
    uniform: bool = False,
) -> list[Term | Sentence | Paragraph]:
    """Select a mixed set of entries, optionally filtered by domain/difficulty.

    Paragraphs are excluded — they are too long for single-line CLI input.
    Use ``qebench judge`` to evaluate paragraph translations instead.

    By default the draw is weighted towards entries that need a second
    annotator, and entries *username* has already attempted are dropped —
    repeating yourself adds no annotator coverage.  If that would empty the
    pool the unfiltered pool is used instead.  Pass ``uniform=True`` for a
    plain uniform shuffle.
    """
    pool: list[Term | Sentence | Paragraph] = [*terms, *sentences]

    if domain:
        pool = [e for e in pool if e.domain == domain]
    if difficulty:
        pool = [e for e in pool if e.difficulty == Difficulty(difficulty)]

    if not pool:
        return []

    if uniform:
        random.shuffle(pool)
        return pool[:count]

    if coverage is None:
        coverage = _annotator_coverage()

    # Never re-serve an entry this user has already attempted.
    candidates = [e for e in pool if username not in coverage.get(e.id, _NO_ANNOTATORS)]
    if not candidates:
        candidates = pool

    weights = [_entry_weight(e.id, coverage, username) for e in candidates]
    return _weighted_sample(candidates, weights, count)


def _render_entry(entry: Term | Sentence | Paragraph) -> Panel:
    """Render an entry as a Rich panel showing the English text."""
    entry_type = entry.id.split("-")[0].upper()
    meta = f"[dim]{entry.id} · {entry.domain} · {entry.difficulty.value}[/dim]"

    body = entry.en

    # Show a random context sentence for terms that have them
    if isinstance(entry, Term) and entry.contexts:
        ctx = random.choice(entry.contexts)
        body += f"\n\n[dim italic]Context: \"{escape(ctx.text)}\"[/dim italic]"

    return Panel(
        f"{body}\n\n{meta}",
        title=f"[bold cyan]{entry_type}[/bold cyan]",
        border_style="cyan",
        padding=(1, 2),
    )


def _reference_panel(
    attempt: str, reference: str, alternatives: list[str], similarity: float,
) -> Panel:
    """Show the user's answer alongside the reference with similarity info."""
    table = Table(show_header=False, border_style="dim", padding=(0, 2))
    table.add_column("Label", style="dim")
    table.add_column("Text")

    table.add_row("Your answer:", f"[bold]{attempt}[/bold]")
    table.add_row("Reference:", f"[green]{reference}[/green]")
    if alternatives:
        table.add_row("Alternatives:", f"[dim]{', '.join(alternatives)}[/dim]")
    table.add_row("Similarity:", f"[cyan]{similarity:.0%}[/cyan]")

    all_valid = [reference.strip(), *(a.strip() for a in alternatives)]
    if attempt.strip() in all_valid:
        note = "[green]Matches the reference exactly.[/green]"
    elif similarity >= DIFF_THRESHOLD:
        note = "[green]Very close to the reference.[/green]"
    else:
        note = "[cyan]A different translation — we'll ask why below.[/cyan]"

    table.add_row("", note)

    return Panel(table, title="[bold]Reference[/bold]", border_style="green")


def _save_attempt(
    entry_id: str,
    attempt: str,
    reference: str,
    confidence: int,
    similarity: float,
    diff_reason: str,
    notes: str,
    username: str,
) -> None:
    """Save a translation attempt to results."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    filepath = RESULTS_DIR / f"{username}.jsonl"

    record: dict = {
        "entry_id": entry_id,
        "attempt": attempt,
        "reference": reference,
        "confidence": confidence,
        "similarity": round(similarity, 4),
        "timestamp": datetime.now(UTC).isoformat(),
        "cli_version": __version__,
    }
    if diff_reason:
        record["diff_reason"] = diff_reason
    if notes:
        record["notes"] = notes

    with open(filepath, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def translate(
    count: int = 5,
    domain: str | None = None,
    difficulty: str | None = None,
    uniform: bool = False,
) -> None:
    """Translate English to Chinese — collecting human translation data.

    Presents English text, collects your translation and confidence level,
    then shows the reference for learning.  Every translation — even ones
    that differ from the reference — is valuable data that helps us
    understand translation variation and cultural nuance.

    Entries are drawn with a bias towards those only one other annotator has
    attempted, so sessions build consensus coverage; *uniform* disables that.
    """
    username = get_github_username()
    terms, sentences, paragraphs = load_all()

    if not terms and not sentences and not paragraphs:
        console.print("[red]No entries in dataset. Run 'qebench add' first.[/red]")
        raise SystemExit(1)

    # Loaded even in uniform mode so the session panel still reports honestly.
    coverage = _annotator_coverage()
    entries = _pick_entries(
        terms, sentences, paragraphs, domain, difficulty, count,
        username=username, coverage=coverage, uniform=uniform,
    )
    if not entries:
        console.print("[red]No entries match your filters.[/red]")
        raise SystemExit(1)

    needs_second = sum(
        1 for e in entries if _needs_second_annotator(e.id, coverage, username)
    )
    mode = "uniform" if uniform else "consensus-weighted"

    console.print()
    console.print(
        Panel(
            f"  Entries: [bold]{len(entries)}[/bold]   "
            f"Domain: [cyan]{domain or 'all'}[/cyan]   "
            f"Difficulty: [yellow]{difficulty or 'all'}[/yellow]   "
            f"User: [green]{username}[/green]\n"
            f"  Need a 2nd annotator: [magenta]{needs_second}/{len(entries)}[/magenta]   "
            f"Selection: [dim]{mode}[/dim]",
            title="[bold]Translation Session[/bold]",
            border_style="blue",
        )
    )

    completed = 0

    for i, entry in enumerate(entries, 1):
        console.print(f"\n[dim]── {i}/{len(entries)} ──[/dim]")
        console.print(_render_entry(entry))

        attempt = questionary.text("Your translation (中文):").ask()
        if attempt is None:
            console.print("[yellow]Session ended early.[/yellow]")
            break

        if not attempt.strip():
            console.print("[dim]Skipped.[/dim]")
            continue

        # Ask confidence level
        confidence = questionary.select(
            "How confident are you?",
            choices=CONFIDENCE_CHOICES,
            use_shortcuts=True,
        ).ask()
        if confidence is None:
            console.print("[yellow]Session ended early.[/yellow]")
            break

        # Get reference and alternatives
        reference = entry.zh
        alternatives = entry.alternatives if isinstance(entry, Term) else []

        # Compute similarity and show reference panel
        similarity = _char_overlap(attempt.strip(), reference)
        console.print(_reference_panel(attempt.strip(), reference, alternatives, similarity))

        # If translation differs, ask why
        diff_reason = ""
        notes = ""
        all_valid = [reference.strip(), *(a.strip() for a in alternatives)]
        if attempt.strip() not in all_valid and similarity < DIFF_THRESHOLD:
            reason = questionary.select(
                "Why does your translation differ?",
                choices=DIFF_REASON_CHOICES,
                use_shortcuts=True,
            ).ask()
            if reason is None:
                console.print("[yellow]Session ended early.[/yellow]")
                break
            diff_reason = reason

            # Ask for notes (especially useful for "other")
            notes_answer = questionary.text(
                "Notes (optional — explain further):",
                default="",
            ).ask()
            if notes_answer is None:
                notes_answer = ""
            notes = notes_answer.strip()

        completed += 1

        # Save result
        _save_attempt(
            entry.id, attempt.strip(), reference, confidence,
            similarity, diff_reason, notes, username,
        )

    # Session summary
    if completed > 0:
        xp_earned = award_xp(username, "translate", completed)
        total_xp = load_xp(username)

        console.print()
        summary = Table(show_header=False, border_style="dim", padding=(0, 2))
        summary.add_column("Label", style="dim")
        summary.add_column("Value", style="bold")
        summary.add_row("Completed:", f"{completed}/{len(entries)}")
        summary.add_row("XP earned:", f"+{xp_earned}")
        summary.add_row("Total XP:", str(total_xp))

        console.print(
            Panel(summary, title="[bold]Session Summary[/bold]", border_style="blue")
        )
    console.print()
