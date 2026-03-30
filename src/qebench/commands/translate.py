"""translate command — Interactive translation practice mode.

The main engagement loop: shows English text, collects user's Chinese
translation, then reveals the reference translation and scores the attempt.
"""

from __future__ import annotations

import json
import random
from datetime import datetime, timezone
from pathlib import Path

import questionary
from rich.columns import Columns
from rich.panel import Panel
from rich.table import Table

from qebench.models import Difficulty, Paragraph, Sentence, Term
from qebench.scoring.xp import XP_TRANSLATE, award_xp, load_xp
from qebench.utils.dataset import DATA_DIR, get_domains, load_all
from qebench.utils.display import console


RESULTS_DIR = DATA_DIR.parent / "results" / "translations"


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

    return Panel(
        f"{entry.en}\n\n{meta}",
        title=f"[bold cyan]{entry_type}[/bold cyan]",
        border_style="cyan",
        padding=(1, 2),
    )


def _score_panel(attempt: str, reference: str, alternatives: list[str]) -> Panel:
    """Show scoring comparison between attempt and reference."""
    overlap = _char_overlap(attempt, reference)

    # Check for exact match with reference or alternatives
    all_valid = [reference, *alternatives]
    exact_match = attempt.strip() in [v.strip() for v in all_valid]

    table = Table(show_header=False, border_style="dim", padding=(0, 2))
    table.add_column("Label", style="dim")
    table.add_column("Text")

    table.add_row("Your answer:", f"[bold]{attempt}[/bold]")
    table.add_row("Reference:", f"[green]{reference}[/green]")
    if alternatives:
        table.add_row("Alternatives:", f"[dim]{', '.join(alternatives)}[/dim]")

    if exact_match:
        score_text = "[bold green]★ Exact match![/bold green]"
    elif overlap >= 0.7:
        score_text = f"[bold yellow]◉ Close! ({overlap:.0%} overlap)[/bold yellow]"
    elif overlap >= 0.4:
        score_text = f"[yellow]○ Partial ({overlap:.0%} overlap)[/yellow]"
    else:
        score_text = f"[red]△ Keep practicing ({overlap:.0%} overlap)[/red]"

    table.add_row("Score:", score_text)

    return Panel(table, title="[bold]Result[/bold]", border_style="green" if exact_match else "yellow")


def _save_attempt(
    entry_id: str,
    attempt: str,
    reference: str,
    overlap: float,
    username: str,
) -> None:
    """Save a translation attempt to results."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    filepath = RESULTS_DIR / f"{username}.jsonl"

    record = {
        "entry_id": entry_id,
        "attempt": attempt,
        "reference": reference,
        "overlap": round(overlap, 4),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    with open(filepath, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def translate(
    count: int = 5,
    domain: str | None = None,
    difficulty: str | None = None,
    username: str = "anonymous",
) -> None:
    """Practice translating English to Chinese — the main game loop.

    Presents English text, collects your translation, then shows
    the reference and a similarity score.
    """
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
    total_overlap = 0.0

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

        # Get reference and alternatives
        reference = entry.zh
        alternatives = entry.alternatives if isinstance(entry, Term) else []

        # Show score
        console.print(_score_panel(attempt.strip(), reference, alternatives))

        overlap = _char_overlap(attempt.strip(), reference)
        total_overlap += overlap
        completed += 1

        # Save result
        _save_attempt(entry.id, attempt.strip(), reference, overlap, username)

    # Session summary
    if completed > 0:
        avg_overlap = total_overlap / completed
        xp_earned = award_xp(username, "translate", completed)
        total_xp = load_xp(username)

        console.print()
        summary = Table(show_header=False, border_style="dim", padding=(0, 2))
        summary.add_column("Label", style="dim")
        summary.add_column("Value", style="bold")
        summary.add_row("Completed:", f"{completed}/{len(entries)}")
        summary.add_row("Avg overlap:", f"{avg_overlap:.0%}")
        summary.add_row("XP earned:", f"+{xp_earned}")
        summary.add_row("Total XP:", str(total_xp))

        console.print(
            Panel(summary, title="[bold]Session Summary[/bold]", border_style="blue")
        )
    console.print()
