"""GitHub identity utilities — detect username via gh CLI."""

from __future__ import annotations

import json
import subprocess
from functools import lru_cache

from qebench.utils.display import console

_cached_username: str | None = None


@lru_cache(maxsize=1)
def get_github_username() -> str:
    """Detect the current GitHub username via `gh api user`.

    Returns the login name, or exits with an error if gh is not
    authenticated.  Result is cached for the process lifetime.
    """
    try:
        result = subprocess.run(
            ["gh", "api", "user", "--jq", ".login"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except FileNotFoundError:
        console.print(
            "[red]Error:[/red] GitHub CLI (gh) is not installed.\n"
            "Install it from https://cli.github.com/ then run [bold]gh auth login[/bold]."
        )
        raise SystemExit(1)

    if result.returncode != 0:
        console.print(
            "[red]Error:[/red] Not authenticated with GitHub CLI.\n"
            "Run [bold]gh auth login[/bold] to set up authentication."
        )
        raise SystemExit(1)

    username = result.stdout.strip()
    if not username:
        console.print("[red]Error:[/red] Could not determine GitHub username.")
        raise SystemExit(1)

    return username
