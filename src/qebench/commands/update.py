"""update command — Pull latest code and sync dependencies.

Run this when returning to the project after time away, or whenever
you want to ensure you have the latest data and code from other RAs.
"""

from __future__ import annotations

import subprocess

from rich.panel import Panel

from qebench.utils.display import console


def _run(cmd: list[str], *, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    """Run a shell command and return the result."""
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def update() -> None:
    """Pull latest code and data from GitHub, then sync dependencies."""
    # 1. git pull --rebase
    console.print("[dim]Pulling latest changes...[/dim]")
    pull = _run(["git", "pull", "--rebase", "--quiet"])
    if pull.returncode != 0:
        console.print(f"[red]Error pulling latest changes:[/red]\n{pull.stderr}")
        console.print("Resolve any conflicts, then try again.")
        raise SystemExit(1)

    # Parse how many commits were pulled
    # git pull prints e.g. "Updating abc1234..def5678" when commits arrived,
    # or nothing (empty stdout) when already up to date.
    already_current = "Already up to date" in pull.stdout or not pull.stdout.strip()

    # 2. uv sync --quiet
    console.print("[dim]Syncing dependencies...[/dim]")
    sync = _run(["uv", "sync", "--quiet"])
    if sync.returncode != 0:
        console.print(f"[red]Error syncing dependencies:[/red]\n{sync.stderr}")
        raise SystemExit(1)

    # 3. Success summary
    if already_current:
        status = "[green]✓[/green] Already up to date"
    else:
        status = "[green]✓[/green] Pulled latest changes"

    console.print()
    console.print(
        Panel(
            f"{status}\n[green]✓[/green] Dependencies synced",
            title="[bold]Updated[/bold]",
            border_style="green",
        )
    )
    console.print()
