"""doctor command — Preflight checks for qebench setup."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rich.panel import Panel

from qebench.utils.dataset import CONFIG_PATH, DATA_DIR
from qebench.utils.display import console


def _check(label: str, ok: bool, fix: str = "") -> bool:
    """Print a check result and return whether it passed."""
    if ok:
        console.print(f"  [green]✓[/green] {label}")
    else:
        msg = f"  [red]✗[/red] {label}"
        if fix:
            msg += f"  — [dim]{fix}[/dim]"
        console.print(msg)
    return ok


def _cmd_ok(*args: str) -> tuple[bool, str]:
    """Run a command and return (success, stdout)."""
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=10)
        return r.returncode == 0, r.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False, ""


def doctor() -> None:
    """Run preflight checks for qebench environment."""
    console.print()
    console.print("[bold]Running preflight checks...[/bold]\n")

    passed = 0
    total = 0

    # 1. gh CLI installed
    total += 1
    gh_ok, _ = _cmd_ok("gh", "--version")
    if _check("GitHub CLI (gh) installed", gh_ok, "Install from https://cli.github.com/"):
        passed += 1

    # 2. gh authenticated
    total += 1
    auth_ok, username = _cmd_ok("gh", "api", "user", "--jq", ".login")
    if _check(
        f"GitHub authenticated{f' as [green]{username}[/green]' if username else ''}",
        auth_ok,
        "Run: gh auth login",
    ):
        passed += 1

    # 3. git installed
    total += 1
    git_ok, _ = _cmd_ok("git", "--version")
    if _check("Git installed", git_ok, "Install git"):
        passed += 1

    # 4. Inside a git repo
    total += 1
    repo_ok, _ = _cmd_ok("git", "rev-parse", "--is-inside-work-tree")
    if _check("Inside a git repository", repo_ok, "Clone the repo first"):
        passed += 1

    # 5. Has push access (check remote)
    total += 1
    remote_ok, remote_url = _cmd_ok("git", "remote", "get-url", "origin")
    if _check(
        f"Remote origin configured{f' ({remote_url})' if remote_url else ''}",
        remote_ok,
        "Set up remote: git remote add origin <url>",
    ):
        passed += 1

    # 6. config.yaml exists
    total += 1
    config_ok = CONFIG_PATH.exists()
    if _check("config.yaml found", config_ok, "Missing config.yaml in repo root"):
        passed += 1

    # 7. data/ directory exists with entries
    total += 1
    terms_dir = DATA_DIR / "terms"
    has_data = terms_dir.exists() and any(terms_dir.glob("*.json"))
    if _check("Dataset has entries", has_data, "Run: qebench add"):
        passed += 1

    # 8. uv available
    total += 1
    uv_ok, _ = _cmd_ok("uv", "--version")
    if _check("uv package manager installed", uv_ok, "Install from https://docs.astral.sh/uv/"):
        passed += 1

    # Summary
    console.print()
    if passed == total:
        console.print(
            Panel(
                f"  All {total} checks passed. You're ready to go!",
                title="[bold green]✓ All good[/bold green]",
                border_style="green",
            )
        )
    else:
        console.print(
            Panel(
                f"  {passed}/{total} checks passed. Fix the issues above.",
                title="[bold yellow]⚠ Issues found[/bold yellow]",
                border_style="yellow",
            )
        )
    console.print()
