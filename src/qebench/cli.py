"""qebench CLI — entry point and command routing."""

from __future__ import annotations

import typer

from qebench.commands.stats import stats

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


if __name__ == "__main__":
    app()
