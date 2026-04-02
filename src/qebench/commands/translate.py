"""translate command — Interactive translation data collection.

The main engagement loop: shows English text, collects the user's Chinese
translation and a confidence rating, then reveals the reference with a
character-similarity score.  When the translation differs from the reference,
the user is prompted for the reason (formal/informal register, regional
preference, context, etc.).  This captures both the *variation* and the
*why* behind it — valuable data for improving our translator.
"""

from __future__ import annotations

import json
import random
from datetime import UTC, datetime

import questionary
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

CONFIDENCE_CHOICES = [
    questionary.Choice("1 — Guessing", value=1),
    questionary.Choice("2 — Uncertain", value=2),
    questionary.Choice("3 — Reasonable", value=3),
    questionary.Choice("4 — Confident", value=4),
    questionary.Choice("5 — Very confident", value=5),
]

DIFF_REASON_CHOICES = [
    questionary.Choice("Formal/written register (书面语)", value="formal-register"),
    questionary.Choice("Informal/spoken register (口语)", value="informal-register"),
    questionary.Choice("Regional preference", value="regional"),
    questionary.Choice("Contextual — depends on usage", value="contextual"),
    questionary.Choice("Abbreviation or shorthand", value="abbreviation"),
    questionary.Choice("Alternative technical term", value="alt-technical"),
    questionary.Choice("Other (explain in notes)", value="other"),
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


def _pick_entries(
    terms: list[Term],
    sentences: list[Sentence],
    paragraphs: list[Paragraph],
    domain: str | None,
    difficulty: str | None,
    count: int,
) -> list[Term | Sentence | Paragraph]:
    """Select a mixed set of entries, optionally filtered by domain/difficulty."""
    pool: list[Term | Sentence | Paragraph] = [*terms, *sentences, *paragraphs]

    if domain:
        pool = [e for e in pool if e.domain == domain]
    if difficulty:
        pool = [e for e in pool if e.difficulty == Difficulty(difficulty)]

    if not pool:
        return []

    random.shuffle(pool)
    return pool[:count]


def _render_entry(entry: Term | Sentence | Paragraph) -> Panel:
    """Render an entry as a Rich panel showing the English text."""
    entry_type = entry.id.split("-")[0].upper()
    meta = f"[dim]{entry.id} · {entry.domain} · {entry.difficulty.value}[/dim]"

    body = entry.en

    # Show a random context sentence for terms that have them
    if isinstance(entry, Term) and entry.contexts:
        ctx = random.choice(entry.contexts)
        body += f"\n\n[dim italic]Context: \"{ctx.text}\"[/dim italic]"

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
) -> None:
    """Translate English to Chinese — collecting human translation data.

    Presents English text, collects your translation and confidence level,
    then shows the reference for learning.  Every translation — even ones
    that differ from the reference — is valuable data that helps us
    understand translation variation and cultural nuance.
    """
    username = get_github_username()
    terms, sentences, paragraphs = load_all()

    if not terms and not sentences and not paragraphs:
        console.print("[red]No entries in dataset. Run 'qebench add' first.[/red]")
        raise SystemExit(1)

    entries = _pick_entries(terms, sentences, paragraphs, domain, difficulty, count)
    if not entries:
        console.print("[red]No entries match your filters.[/red]")
        raise SystemExit(1)

    console.print()
    console.print(
        Panel(
            f"  Entries: [bold]{len(entries)}[/bold]   "
            f"Domain: [cyan]{domain or 'all'}[/cyan]   "
            f"Difficulty: [yellow]{difficulty or 'all'}[/yellow]   "
            f"User: [green]{username}[/green]",
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
