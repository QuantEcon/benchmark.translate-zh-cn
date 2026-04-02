"""update command — Pull latest code, sync dependencies, and enrich term contexts.

Run this when returning to the project after time away, or whenever
you want to ensure you have the latest data and code from other RAs.
Also clones/updates QuantEcon lecture repos and extracts context
sentences for terms that are missing them.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from rich.panel import Panel

from qebench.utils.context import GITHUB_ORG, LECTURE_REPOS, enrich_terms
from qebench.utils.dataset import DATA_DIR, load_terms
from qebench.utils.display import console

# Lecture repos are cached here (gitignored)
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
CACHE_DIR = _REPO_ROOT / ".cache" / "lectures"


def _run(cmd: list[str], *, timeout: int = 60, **kwargs: object) -> subprocess.CompletedProcess[str]:
    """Run a shell command and return the result."""
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        **kwargs,
    )


def _sync_lecture_repos() -> list[Path]:
    """Clone or pull each lecture repo into .cache/lectures/. Returns repo dirs."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    dirs: list[Path] = []

    for repo_name in LECTURE_REPOS:
        repo_dir = CACHE_DIR / repo_name
        if repo_dir.is_dir():
            console.print(f"[dim]  Updating {repo_name}...[/dim]")
            result = _run(
                ["git", "pull", "--rebase", "--quiet"],
                timeout=120,
                cwd=str(repo_dir),
            )
            if result.returncode != 0:
                console.print(f"[yellow]  Warning: failed to pull {repo_name}, using cached version[/yellow]")
        else:
            console.print(f"[dim]  Cloning {repo_name}...[/dim]")
            url = f"https://github.com/{GITHUB_ORG}/{repo_name}.git"
            result = _run(
                ["git", "clone", "--depth", "1", "--quiet", url, str(repo_dir)],
                timeout=300,
            )
            if result.returncode != 0:
                console.print(f"[yellow]  Warning: failed to clone {repo_name}[/yellow]")
                continue
        dirs.append(repo_dir)

    return dirs


def _enrich_term_contexts(lecture_dirs: list[Path]) -> int:
    """Load terms, enrich with context sentences, write back to JSON files."""
    terms = load_terms()
    if not terms:
        return 0

    enriched_ids = enrich_terms(terms, lecture_dirs)
    if not enriched_ids:
        return 0

    # Only rewrite files that contain enriched terms
    terms_dir = DATA_DIR / "terms"
    for path in sorted(terms_dir.glob("*.json")):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        is_wrapper = isinstance(data, dict) and "entries" in data
        items = data.get("entries", []) if is_wrapper else data
        ids_in_file = {item["id"] for item in items}

        # Skip files with no enriched terms
        if not ids_in_file & enriched_ids:
            continue

        terms_for_file = [t for t in terms if t.id in ids_in_file]
        entries_data = [t.model_dump(exclude_none=True) for t in terms_for_file]

        # Preserve wrapper format if original file used it
        if is_wrapper:
            output = {**data, "entries": entries_data}
        else:
            output = entries_data

        with open(path, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
            f.write("\n")

    return len(enriched_ids)


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
    already_current = "Already up to date" in pull.stdout or not pull.stdout.strip()

    # 2. uv sync --quiet
    console.print("[dim]Syncing dependencies...[/dim]")
    sync = _run(["uv", "sync", "--quiet"])
    if sync.returncode != 0:
        console.print(f"[red]Error syncing dependencies:[/red]\n{sync.stderr}")
        raise SystemExit(1)

    # 3. Sync lecture repos and enrich term contexts
    console.print("[dim]Syncing lecture repos...[/dim]")
    lecture_dirs = _sync_lecture_repos()

    enriched = 0
    if lecture_dirs:
        console.print("[dim]Enriching term contexts...[/dim]")
        enriched = _enrich_term_contexts(lecture_dirs)

    # 4. Success summary
    if already_current:
        status = "[green]✓[/green] Already up to date"
    else:
        status = "[green]✓[/green] Pulled latest changes"

    context_line = (
        f"[green]✓[/green] Enriched {enriched} terms with context sentences"
        if enriched > 0
        else "[green]✓[/green] Term contexts up to date"
    )

    console.print()
    console.print(
        Panel(
            f"{status}\n[green]✓[/green] Dependencies synced\n{context_line}",
            title="[bold]Updated[/bold]",
            border_style="green",
        )
    )
    console.print()
