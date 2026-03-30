# Contributing

## Setup

```bash
git clone https://github.com/QuantEcon/benchmark.translate-zh-cn.git
cd benchmark.translate-zh-cn
uv sync --extra dev
```

## Running Tests

```bash
uv run pytest tests/ -v
```

All tests should pass before submitting a PR.

## Code Style

We use [ruff](https://docs.astral.sh/ruff/) for linting and formatting:

```bash
uv run ruff check src/ tests/
uv run ruff format src/ tests/
```

## Project Structure

- `src/qebench/` — main package code
- `tests/` — pytest tests
- `data/` — benchmark dataset (JSON files)
- `results/` — output data (translation attempts, XP, Elo)
- `docs/` — documentation

See [Architecture](architecture.md) for the full module map.

## Adding a New Command

1. Create `src/qebench/commands/yourcommand.py` with a function
2. Register it in `src/qebench/cli.py` via `app.command()`
3. Add tests in `tests/test_yourcommand.py`
4. Document in `docs/user/cli-reference.md`

## Adding Data Entries

Use `qebench add` for interactive entry creation. For bulk imports, write a
script in `scripts/` following the pattern in `scripts/seed_from_glossary.py`.

## Branch Workflow

- Work on a feature branch
- Open a PR against `main`
- All tests must pass
- Get review from a team member
