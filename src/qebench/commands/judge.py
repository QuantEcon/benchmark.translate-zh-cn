"""judge command — Anonymous head-to-head translation comparison.

Shows an English source text alongside two anonymous translations.
The user rates each on accuracy and fluency, then picks a winner.
Results update Elo ratings and earn XP.
"""

from __future__ import annotations

import itertools
import json
import random
from datetime import UTC, datetime

import questionary
from rich.columns import Columns
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

from qebench import __version__
from qebench.models import Paragraph, Sentence, Term
from qebench.scoring.formatting import formatting_score
from qebench.scoring.glossary import glossary_compliance, reference_overlap
from qebench.scoring.judgments import record_consensus, record_judgment, update_model_elos
from qebench.scoring.xp import award_xp, load_xp
from qebench.utils.dataset import RESULTS_DIR, load_all, load_terms
from qebench.utils.display import console
from qebench.utils.github import get_github_username

MODEL_OUTPUTS_DIR = RESULTS_DIR / "model-outputs"

SCORE_CHOICES = [questionary.Choice(str(i), value=i, shortcut_key=str(i)) for i in range(6)]

WINNER_CHOICES = [
    questionary.Choice("A is better", value="a", shortcut_key="a"),
    questionary.Choice("B is better", value="b", shortcut_key="b"),
    questionary.Choice("Tie — equally good", value="tie", shortcut_key="t"),
    questionary.Choice("Neither — both are poor", value="neither", shortcut_key="n"),
]


def _load_model_outputs() -> dict[str, dict[str, str]]:
    """Load all model outputs, keyed by model:prompt label then entry_id.

    Keys use the format ``model:prompt_template`` (e.g.
    ``claude-sonnet-4-6:academic``) when a ``prompt_template`` field is
    present, or plain ``model`` as a fallback for older records.

    Returns:
        {label: {entry_id: translated_text, ...}, ...}
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
                prompt = record.get("prompt_template", "")
                # Key by model:prompt so different prompts are distinct
                label = f"{model}:{prompt}" if prompt else model
                entry_id = record.get("entry_id", "")
                translated = record.get("translated_text", "")
                if entry_id and translated:
                    outputs.setdefault(label, {})[entry_id] = translated

    return outputs


def _build_matchups(
    entries: list[Term | Sentence | Paragraph],
    model_outputs: dict[str, dict[str, str]],
) -> list[dict]:
    """Build a list of matchup dicts for judging.

    Each matchup has: entry, translation_a, translation_b, label_a, label_b.
    Labels are the real model names (hidden from user during judging).

    Strategy:
    - If 2+ models have output for an entry → prefer a pair with different
      translations so judges have something meaningful to compare.
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
            # Try to find a pair with different translations
            pairs = list(itertools.combinations(available, 2))
            diff_pairs = [(a, b) for a, b in pairs if a[1].strip() != b[1].strip()]
            if diff_pairs:
                pair = list(random.choice(diff_pairs))
            else:
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

    # Separate into disagreements and consensus, then interleave so the
    # user always gets a mix of both (disagreements are more interesting
    # but consensus ratings are still valuable).
    diff_matchups = [m for m in matchups if m["translation_a"].strip() != m["translation_b"].strip()]
    same_matchups = [m for m in matchups if m["translation_a"].strip() == m["translation_b"].strip()]

    interleaved: list[dict] = []
    di, si = 0, 0
    while di < len(diff_matchups) or si < len(same_matchups):
        # Alternate: diff, same, diff, same, ...
        if di < len(diff_matchups):
            interleaved.append(diff_matchups[di])
            di += 1
        if si < len(same_matchups):
            interleaved.append(same_matchups[si])
            si += 1

    return interleaved


def _render_source(entry: Term | Sentence | Paragraph, round_num: int) -> Panel:
    """Render the English source text panel."""
    entry_type = entry.id.split("-")[0].upper()
    meta = f"[dim]{entry.id} · {entry.domain} · {entry.difficulty.value}[/dim]"
    body = f"[bold]{escape(entry.en)}[/bold]\n\n{meta}"
    if isinstance(entry, Term) and entry.contexts:
        ctx = escape(entry.contexts[0].text)
        body += f"\n\n[dim italic]Context: {ctx}[/dim italic]"
    return Panel(
        body,
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

    # Formatting fidelity scores (if entry has source text)
    source_text = getattr(entry, "en", "")
    if source_text:
        fmt_a = formatting_score(source_text, text_a)
        fmt_b = formatting_score(source_text, text_b)
        table.add_row(
            "Fullwidth punct.",
            f"{fmt_a['fullwidth_punctuation']:.0%}",
            f"{fmt_b['fullwidth_punctuation']:.0%}",
        )
        if not fmt_a["directive_balance"] or not fmt_b["directive_balance"]:
            table.add_row(
                "Directive balance",
                "[green]✓[/green]" if fmt_a["directive_balance"] else "[red]✗[/red]",
                "[green]✓[/green]" if fmt_b["directive_balance"] else "[red]✗[/red]",
            )

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

        # Identical translations — ask human to rate the consensus
        if text_a.strip() == text_b.strip():
            skipped_identical += 1
            console.print(f"\n[dim]── Round {i}/{len(matchups)} ──[/dim]")
            console.print(_render_source(entry, i))

            consensus_text = text_a.strip()
            is_ref_match = label_a == "human-reference" or label_b == "human-reference"
            header = "Model matches reference:" if is_ref_match else "All models agree:"
            console.print(
                Panel(
                    f"{header}\n\n[bold]{consensus_text}[/bold]",
                    title="[bold green]Consensus[/bold green]",
                    border_style="green",
                    padding=(1, 2),
                )
            )

            c_acc = questionary.select(
                "Accuracy (0-5):", choices=SCORE_CHOICES, use_shortcuts=True,
            ).ask()
            if c_acc is None:
                console.print("[yellow]Session ended early.[/yellow]")
                break
            c_flu = questionary.select(
                "Fluency (0-5):", choices=SCORE_CHOICES, use_shortcuts=True,
            ).ask()
            if c_flu is None:
                console.print("[yellow]Session ended early.[/yellow]")
                break

            suggestion = ""
            if c_acc <= 2 or c_flu <= 2:
                suggestion = questionary.text(
                    "Suggest a better translation (optional):",
                ).ask() or ""

            consensus_models = [
                lbl for lbl in (label_a, label_b) if lbl != "human-reference"
            ]

            record_consensus(
                username=username,
                entry_id=entry.id,
                models=consensus_models,
                translation=consensus_text,
                accuracy=c_acc,
                fluency=c_flu,
                reference=entry.zh,
                domain=entry.domain,
                difficulty=entry.difficulty.value,
                suggestion=suggestion,
                timestamp=datetime.now(UTC).isoformat(),
                cli_version=__version__,
            )
            completed += 1
            continue

        console.print(f"\n[dim]── Round {i}/{len(matchups)} ──[/dim]")
        console.print(_render_source(entry, i))
        console.print(_render_translations(text_a, text_b))

        # Ask winner FIRST (#9)
        winner_answer = questionary.select(
            "Which is better overall?",
            choices=WINNER_CHOICES,
            use_shortcuts=True,
        ).ask()
        if winner_answer is None:
            console.print("[yellow]Session ended early.[/yellow]")
            break

        # For "neither", skip detailed scoring; ties still collect ratings
        suggestion = ""
        if winner_answer == "neither":
            acc_a = acc_b = flu_a = flu_b = None
            suggestion = questionary.text(
                "Suggest a better translation (optional):",
            ).ask() or ""
        else:
            # Collect scores for A
            console.print("\n[bold yellow]Rate Translation A:[/bold yellow]")
            acc_a = questionary.select("  Accuracy (0-5):", choices=SCORE_CHOICES, use_shortcuts=True).ask()
            if acc_a is None:
                console.print("[yellow]Session ended early.[/yellow]")
                break
            flu_a = questionary.select("  Fluency (0-5):", choices=SCORE_CHOICES, use_shortcuts=True).ask()
            if flu_a is None:
                console.print("[yellow]Session ended early.[/yellow]")
                break

            # Collect scores for B
            console.print("[bold magenta]Rate Translation B:[/bold magenta]")
            acc_b = questionary.select("  Accuracy (0-5):", choices=SCORE_CHOICES, use_shortcuts=True).ask()
            if acc_b is None:
                console.print("[yellow]Session ended early.[/yellow]")
                break
            flu_b = questionary.select("  Fluency (0-5):", choices=SCORE_CHOICES, use_shortcuts=True).ask()
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
            translation_a=text_a,
            translation_b=text_b,
            reference=entry.zh,
            domain=entry.domain,
            difficulty=entry.difficulty.value,
            suggestion=suggestion,
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
            summary.add_row("Consensus rated:", str(skipped_identical))
        summary.add_row("XP earned:", f"+{xp_earned}")
        summary.add_row("Total XP:", str(total_xp))

        console.print(
            Panel(summary, title="[bold]Session Summary[/bold]", border_style="blue")
        )
    console.print()
