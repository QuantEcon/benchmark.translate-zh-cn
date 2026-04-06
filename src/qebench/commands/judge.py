"""judge command — Anonymous head-to-head translation comparison.

Shows an English source text alongside two anonymous translations.
The user rates each on accuracy and fluency, then picks a winner.
Results update Elo ratings and earn XP.
"""

from __future__ import annotations

import json
import random
from datetime import UTC, datetime

import questionary
from rich.columns import Columns
from rich.panel import Panel
from rich.table import Table

from qebench import __version__
from qebench.models import Paragraph, Sentence, Term
from qebench.scoring.glossary import glossary_compliance, reference_overlap
from qebench.scoring.judgments import record_judgment, update_model_elos
from qebench.scoring.xp import award_xp, load_xp
from qebench.utils.dataset import RESULTS_DIR, load_all, load_terms
from qebench.utils.display import console
from qebench.utils.github import get_github_username

MODEL_OUTPUTS_DIR = RESULTS_DIR / "model-outputs"

SCORE_CHOICES = [questionary.Choice(str(i), value=i) for i in range(1, 11)]

WINNER_CHOICES = [
    questionary.Choice("A is better", value="a"),
    questionary.Choice("B is better", value="b"),
    questionary.Choice("Tie — equally good", value="tie"),
    questionary.Choice("Neither — both are poor", value="neither"),
]


def _load_model_outputs() -> dict[str, dict[str, str]]:
    """Load all model outputs, keyed by model name then entry_id.

    Returns:
        {model_name: {entry_id: translated_text, ...}, ...}
    """
    outputs: dict[str, dict[str, str]] = {}
    if not MODEL_OUTPUTS_DIR.exists():
        return outputs

    for path in MODEL_OUTPUTS_DIR.glob("*.jsonl"):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                model = record.get("model", "unknown")
                entry_id = record.get("entry_id", "")
                translated = record.get("translated_text", "")
                if entry_id and translated:
                    outputs.setdefault(model, {})[entry_id] = translated

    return outputs


def _build_matchups(
    entries: list[Term | Sentence | Paragraph],
    model_outputs: dict[str, dict[str, str]],
) -> list[dict]:
    """Build a list of matchup dicts for judging.

    Each matchup has: entry, translation_a, translation_b, label_a, label_b.
    Labels are the real model names (hidden from user during judging).

    Strategy:
    - If 2+ models have output for an entry → pair two models
    - If 1 model has output → pair model vs. reference ("human")
    - If 0 model outputs → skip (need at least one model output to judge)
    """
    matchups = []
    models = list(model_outputs.keys())

    for entry in entries:
        available: list[tuple[str, str]] = []  # (label, translation)

        # Add model translations for this entry
        for model_name in models:
            if entry.id in model_outputs[model_name]:
                available.append((model_name, model_outputs[model_name][entry.id]))

        # Need at least 1 model output to make a matchup
        if not available:
            continue

        if len(available) >= 2:
            # Pair two random models
            pair = random.sample(available, 2)
        else:
            # Pair single model vs. reference
            pair = [available[0], ("human-reference", entry.zh)]

        # Randomize A/B assignment so there's no positional bias
        random.shuffle(pair)

        matchups.append({
            "entry": entry,
            "translation_a": pair[0][1],
            "translation_b": pair[1][1],
            "label_a": pair[0][0],
            "label_b": pair[1][0],
        })

    random.shuffle(matchups)
    return matchups


def _render_source(entry: Term | Sentence | Paragraph, round_num: int) -> Panel:
    """Render the English source text panel."""
    entry_type = entry.id.split("-")[0].upper()
    meta = f"[dim]{entry.id} · {entry.domain} · {entry.difficulty.value}[/dim]"
    return Panel(
        f"{entry.en}\n\n{meta}",
        title=f"[bold cyan]Judge[/bold cyan]  [dim](Round {round_num})[/dim]  [dim]{entry_type}[/dim]",
        border_style="cyan",
        padding=(1, 2),
    )


def _render_translations(text_a: str, text_b: str) -> Columns:
    """Render two anonymous translations side by side."""
    panel_a = Panel(
        text_a,
        title="[bold]Translation A[/bold]",
        border_style="yellow",
        padding=(1, 2),
        expand=True,
    )
    panel_b = Panel(
        text_b,
        title="[bold]Translation B[/bold]",
        border_style="magenta",
        padding=(1, 2),
        expand=True,
    )
    return Columns([panel_a, panel_b], equal=True)


def _render_result(
    winner: str,
    label_a: str,
    label_b: str,
    elo_a: float,
    elo_b: float,
    reference: str,
    entry: Term | Sentence | Paragraph,
    term_translations: list[str],
    text_a: str,
    text_b: str,
) -> Panel:
    """Render the reveal panel showing who won and automated scores."""
    winner_text = {
        "a": f"[yellow]A ({label_a})[/yellow] wins!",
        "b": f"[magenta]B ({label_b})[/magenta] wins!",
        "tie": "[dim]Tie[/dim]",
        "neither": "[red]Neither — both poor[/red]",
    }[winner]

    # Automated scores
    overlap_a = reference_overlap(text_a, reference)
    overlap_b = reference_overlap(text_b, reference)
    glossary_a = glossary_compliance(text_a, term_translations)
    glossary_b = glossary_compliance(text_b, term_translations)

    table = Table(show_header=True, border_style="dim", padding=(0, 1))
    table.add_column("", style="dim")
    table.add_column(f"A ({label_a})", justify="center")
    table.add_column(f"B ({label_b})", justify="center")
    if winner == "a":
        table.add_row("Winner", winner_text, "")
    elif winner == "b":
        table.add_row("Winner", "", winner_text)
    else:
        table.add_row("Winner", winner_text, winner_text)
    table.add_row("Elo", f"{elo_a:.0f}", f"{elo_b:.0f}")
    table.add_row("Ref. overlap", f"{overlap_a:.0%}", f"{overlap_b:.0%}")
    if term_translations:
        table.add_row("Glossary", f"{glossary_a:.0%}", f"{glossary_b:.0%}")

    return Panel(table, title="[bold]Result[/bold]", border_style="green")


def _get_key_term_translations(
    entry: Term | Sentence | Paragraph,
    all_terms: list[Term],
) -> list[str]:
    """Get Chinese translations for key terms linked to this entry."""
    if isinstance(entry, Term):
        return []  # Terms don't have key_terms
    key_ids = set(getattr(entry, "key_terms", []))
    if not key_ids:
        return []
    return [t.zh for t in all_terms if t.id in key_ids]


def judge(
    count: int = 10,
    domain: str | None = None,
) -> None:
    """Judge anonymous translations head-to-head.

    Shows two anonymous translations of the same source text.
    Rate each on accuracy and fluency, pick a winner.
    Results update Elo ratings for the models.
    """
    username = get_github_username()

    # Load dataset and model outputs
    terms, sentences, paragraphs = load_all()
    all_entries: list[Term | Sentence | Paragraph] = [*terms, *sentences, *paragraphs]

    if domain:
        all_entries = [e for e in all_entries if e.domain == domain]

    if not all_entries:
        console.print("[red]No entries found matching filters.[/red]")
        raise SystemExit(1)

    model_outputs = _load_model_outputs()
    if not model_outputs:
        console.print("[red]No model outputs found. Run 'qebench run' first to generate translations.[/red]")
        raise SystemExit(1)

    matchups = _build_matchups(all_entries, model_outputs)
    if not matchups:
        console.print("[red]No matchups available — models haven't translated any of the filtered entries.[/red]")
        raise SystemExit(1)

    if count > 0:
        matchups = matchups[:count]

    all_terms = load_terms()

    console.print()
    console.print(
        Panel(
            f"  Rounds: [bold]{len(matchups)}[/bold]   "
            f"Domain: [cyan]{domain or 'all'}[/cyan]   "
            f"Models: [yellow]{len(model_outputs)}[/yellow]   "
            f"User: [green]{username}[/green]",
            title="[bold]Judge Session[/bold]",
            border_style="blue",
        )
    )

    completed = 0
    skipped_identical = 0

    for i, matchup in enumerate(matchups, 1):
        entry = matchup["entry"]
        text_a = matchup["translation_a"]
        text_b = matchup["translation_b"]
        label_a = matchup["label_a"]
        label_b = matchup["label_b"]

        # Skip identical translations — auto-record a tie (#9)
        if text_a.strip() == text_b.strip():
            skipped_identical += 1
            console.print(
                f"\n[dim]── Round {i}/{len(matchups)} ──[/dim]"
            )
            console.print(
                f"[dim]Both identical ({text_a.strip()[:30]}…) — auto-tie, skipping.[/dim]"
                if len(text_a.strip()) > 30
                else f"[dim]Both identical ({text_a.strip()}) — auto-tie, skipping.[/dim]"
            )

            is_reference = label_a == "human-reference" or label_b == "human-reference"
            if is_reference:
                elo_a = elo_b = 0.0
            else:
                elo_a, elo_b = update_model_elos(label_a, label_b, "tie")

            record_judgment(
                username=username,
                entry_id=entry.id,
                model_a=label_a,
                model_b=label_b,
                winner="tie",
                score_a_accuracy=None,
                score_a_fluency=None,
                score_b_accuracy=None,
                score_b_fluency=None,
                timestamp=datetime.now(UTC).isoformat(),
                cli_version=__version__,
            )
            completed += 1
            continue

        console.print(f"\n[dim]── Round {i}/{len(matchups)} ──[/dim]")
        console.print(_render_source(entry, i))
        console.print(_render_translations(text_a, text_b))

        # Ask winner FIRST (#9)
        winner_answer = questionary.rawselect(
            "Which is better overall?",
            choices=WINNER_CHOICES,
        ).ask()
        if winner_answer is None:
            console.print("[yellow]Session ended early.[/yellow]")
            break

        # For ties and neither, skip detailed scoring (#9)
        if winner_answer in ("tie", "neither"):
            acc_a = acc_b = flu_a = flu_b = None
        else:
            # Collect scores for A
            console.print("\n[bold yellow]Rate Translation A:[/bold yellow]")
            acc_a = questionary.rawselect("  Accuracy (1-10):", choices=SCORE_CHOICES).ask()
            if acc_a is None:
                console.print("[yellow]Session ended early.[/yellow]")
                break
            flu_a = questionary.rawselect("  Fluency (1-10):", choices=SCORE_CHOICES).ask()
            if flu_a is None:
                console.print("[yellow]Session ended early.[/yellow]")
                break

            # Collect scores for B
            console.print("[bold magenta]Rate Translation B:[/bold magenta]")
            acc_b = questionary.rawselect("  Accuracy (1-10):", choices=SCORE_CHOICES).ask()
            if acc_b is None:
                console.print("[yellow]Session ended early.[/yellow]")
                break
            flu_b = questionary.rawselect("  Fluency (1-10):", choices=SCORE_CHOICES).ask()
            if flu_b is None:
                console.print("[yellow]Session ended early.[/yellow]")
                break

        # Update Elo (skip when one side is the human reference)
        is_reference = label_a == "human-reference" or label_b == "human-reference"
        if is_reference:
            elo_a = elo_b = 0.0
        else:
            elo_a, elo_b = update_model_elos(label_a, label_b, winner_answer)

        # Save judgment
        record_judgment(
            username=username,
            entry_id=entry.id,
            model_a=label_a,
            model_b=label_b,
            winner=winner_answer,
            score_a_accuracy=acc_a,
            score_a_fluency=flu_a,
            score_b_accuracy=acc_b,
            score_b_fluency=flu_b,
            timestamp=datetime.now(UTC).isoformat(),
            cli_version=__version__,
        )

        completed += 1

        # Show result
        term_translations = _get_key_term_translations(entry, all_terms)
        console.print(
            _render_result(
                winner_answer, label_a, label_b, elo_a, elo_b,
                entry.zh, entry, term_translations, text_a, text_b,
            )
        )

    # Session summary
    if completed > 0:
        xp_earned = award_xp(username, "judge", completed)
        total_xp = load_xp(username)

        console.print()
        summary = Table(show_header=False, border_style="dim", padding=(0, 2))
        summary.add_column("Label", style="dim")
        summary.add_column("Value", style="bold")
        summary.add_row("Rounds completed:", f"{completed}/{len(matchups)}")
        if skipped_identical:
            summary.add_row("Identical (auto-tie):", str(skipped_identical))
        summary.add_row("XP earned:", f"+{xp_earned}")
        summary.add_row("Total XP:", str(total_xp))

        console.print(
            Panel(summary, title="[bold]Session Summary[/bold]", border_style="blue")
        )
    console.print()
