"""submit command — Pull, commit, and push local changes to GitHub.

Pulls with --rebase before pushing so concurrent work from other RAs
is incorporated automatically.  Per-user data files mean rebase will
always succeed without conflicts.  If push still fails (e.g. another RA
pushed in the same second), just run `qebench submit` again.
"""

from __future__ import annotations

import subprocess

from rich.panel import Panel

from qebench.utils.display import console
from qebench.utils.github import get_github_username


def _run_git(*args: str) -> subprocess.CompletedProcess[str]:
    """Run a git command and return the result."""
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        timeout=30,
    )


def _has_changes() -> bool:
    """Check if there are staged or unstaged changes in data/ or results/."""
    result = _run_git("status", "--porcelain", "data/", "results/")
    return bool(result.stdout.strip())


def submit() -> None:
    """Pull latest changes, commit data and results, and push to GitHub."""
    username = get_github_username()

    # 1. Check for local changes
    if not _has_changes():
        console.print("[yellow]Nothing to submit — no changes in data/ or results/.[/yellow]")
        return

    # 2. Pull with rebase to avoid merge commits
    console.print("[dim]Pulling latest changes...[/dim]")
    pull = _run_git("pull", "--rebase", "--quiet")
    if pull.returncode != 0:
        console.print(
            f"[red]Error pulling latest changes:[/red]\n{pull.stderr}"
        )
        console.print("Resolve conflicts manually, then try again.")
        raise SystemExit(1)

    # 3. Stage data/ and results/
    _run_git("add", "data/", "results/")

    # 4. Check if staging produced anything to commit
    staged = _run_git("diff", "--cached", "--name-only")
    if not staged.stdout.strip():
        console.print("[yellow]Nothing to submit after staging.[/yellow]")
        return

    # 5. Count what's being committed
    changed_files = staged.stdout.strip().splitlines()
    data_files = [f for f in changed_files if f.startswith("data/")]
    result_files = [f for f in changed_files if f.startswith("results/")]

    # 6. Commit
    msg = f"qebench: submit by {username}"
    commit = _run_git("commit", "-m", msg)
    if commit.returncode != 0:
        console.print(f"[red]Error committing:[/red]\n{commit.stderr}")
        raise SystemExit(1)

    # 7. Push
    console.print("[dim]Pushing to GitHub...[/dim]")
    push = _run_git("push")
    if push.returncode != 0:
        console.print(f"[red]Error pushing:[/red]\n{push.stderr}")
        console.print("Another RA may have pushed first. Run [bold]qebench submit[/bold] again.")
        raise SystemExit(1)

    # 8. Success summary
    summary_lines = []
    if data_files:
        summary_lines.append(f"  [green]✓[/green] {len(data_files)} data file(s)")
    if result_files:
        summary_lines.append(f"  [green]✓[/green] {len(result_files)} result file(s)")

    console.print()
    console.print(
        Panel(
            "\n".join(summary_lines),
            title=f"[bold]Submitted as {username}[/bold]",
            border_style="green",
        )
    )
    console.print()
