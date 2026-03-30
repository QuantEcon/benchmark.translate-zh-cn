"""stats command — Show dataset coverage, Elo rankings, and leaderboard."""

from __future__ import annotations

from rich.panel import Panel
from rich.table import Table

from qebench.utils.dataset import get_targets, load_all
from qebench.utils.display import console


def _progress_bar(current: int, target: int, width: int = 30) -> str:
    """Render a text-based progress bar."""
    ratio = min(current / target, 1.0) if target > 0 else 0.0
    filled = int(ratio * width)
    bar = "█" * filled + "░" * (width - filled)
    pct = ratio * 100
    return f"{bar}  {current:>4} / {target:<4}  ({pct:.0f}%)"


def _domain_summary(terms: list, sentences: list, paragraphs: list) -> dict[str, int]:
    """Count entries per domain across all levels."""
    counts: dict[str, int] = {}
    for entry in [*terms, *sentences, *paragraphs]:
        d = entry.domain
        counts[d] = counts.get(d, 0) + 1
    return dict(sorted(counts.items(), key=lambda x: -x[1]))


def stats() -> None:
    """Show dataset coverage, domain breakdown, and progress toward targets."""
    terms, sentences, paragraphs = load_all()
    targets = get_targets()

    # Coverage panel
    coverage_lines = [
        f"  [bold]Terms:[/bold]       {_progress_bar(len(terms), targets.get('terms', 500))}",
        f"  [bold]Sentences:[/bold]   {_progress_bar(len(sentences), targets.get('sentences', 100))}",
        f"  [bold]Paragraphs:[/bold]  {_progress_bar(len(paragraphs), targets.get('paragraphs', 30))}",
    ]
    console.print()
    console.print(
        Panel(
            "\n".join(coverage_lines),
            title="[bold]Dataset Coverage[/bold]",
            border_style="blue",
        )
    )

    # Domain breakdown table
    domain_counts = _domain_summary(terms, sentences, paragraphs)
    if domain_counts:
        table = Table(title="Entries by Domain", border_style="dim")
        table.add_column("Domain", style="cyan")
        table.add_column("Count", justify="right", style="green")
        for domain, count in domain_counts.items():
            table.add_row(domain, str(count))
        table.add_row("[bold]Total[/bold]", f"[bold]{sum(domain_counts.values())}[/bold]")
        console.print()
        console.print(table)

    # Quick totals
    console.print()
    total = len(terms) + len(sentences) + len(paragraphs)
    console.print(f"  [dim]{total} entries across {len(domain_counts)} domains[/dim]")
    console.print()
