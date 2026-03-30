"""stats command — Show dataset coverage, leaderboard, and domain breakdown."""

from __future__ import annotations

import json

from rich.panel import Panel
from rich.table import Table

from qebench.scoring.xp import XP_DIR
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


def _load_leaderboard() -> list[dict]:
    """Load XP data for all users, sorted by total XP descending."""
    if not XP_DIR.exists():
        return []
    entries = []
    for path in sorted(XP_DIR.glob("*.json")):
        username = path.stem
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        entries.append({
            "username": username,
            "total": data.get("total", 0),
            "actions": data.get("actions", {}),
        })
    entries.sort(key=lambda e: -e["total"])
    return entries


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

    # Leaderboard
    leaderboard = _load_leaderboard()
    if leaderboard:
        lb = Table(title="Leaderboard", border_style="dim")
        lb.add_column("#", justify="right", style="dim", width=3)
        lb.add_column("User", style="green")
        lb.add_column("XP", justify="right", style="bold yellow")
        lb.add_column("Translate", justify="right", style="cyan")
        lb.add_column("Add", justify="right", style="cyan")
        lb.add_column("Judge", justify="right", style="cyan")
        for rank, entry in enumerate(leaderboard, 1):
            actions = entry["actions"]
            lb.add_row(
                str(rank),
                entry["username"],
                str(entry["total"]),
                str(actions.get("translate", 0)),
                str(actions.get("add", 0)),
                str(actions.get("judge", 0)),
            )
        console.print()
        console.print(lb)

    # Quick totals
    console.print()
    total = len(terms) + len(sentences) + len(paragraphs)
    console.print(f"  [dim]{total} entries across {len(domain_counts)} domains[/dim]")
    console.print()
