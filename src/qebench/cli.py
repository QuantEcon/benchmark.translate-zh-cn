"""qebench CLI — entry point and command routing."""

from __future__ import annotations

from typing import Optional

import typer

from qebench.commands.add import add
from qebench.commands.stats import stats
from qebench.commands.translate import translate as translate_fn

app = typer.Typer(
    name="qebench",
    help="Benchmark CLI for evaluating English-Chinese translation quality.",
    no_args_is_help=True,
)


@app.callback()
def main() -> None:
    """Benchmark CLI for evaluating English-Chinese translation quality."""


# Register commands
app.command("stats", help="Show dataset coverage, domain breakdown, and progress.")(stats)
app.command("add", help="Contribute new terms, sentences, or paragraphs.")(add)


@app.command("translate")
def translate_cmd(
    count: int = typer.Option(5, "--count", "-n", help="Number of entries per session."),
    domain: Optional[str] = typer.Option(None, "--domain", "-d", help="Filter by domain."),
    difficulty: Optional[str] = typer.Option(None, "--difficulty", help="Filter: basic/intermediate/advanced."),
    username: str = typer.Option("anonymous", "--user", "-u", help="Your username for XP tracking."),
) -> None:
    """Practice translating English to Chinese — the main game loop."""
    translate_fn(count=count, domain=domain, difficulty=difficulty, username=username)


if __name__ == "__main__":
    app()
