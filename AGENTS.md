# AGENTS.md

Instructions for AI coding agents working on this repository.

## Project Overview

**benchmark.translate-zh-cn** is a CLI tool (`qebench`) and benchmark dataset for evaluating English-to-Chinese translation quality in economics and mathematics. Built with Python, Typer, Rich, Pydantic.

**Current state**: Phase 2.5 complete — working CLI with `translate`, `add`, `stats`, `export` commands; dashboard website; 314 seeded terms; 69 tests passing.

---

## Module Structure

```
src/qebench/
├── cli.py                 # Typer app — command routing + argument parsing
├── models.py              # Pydantic models: Term, Sentence, Paragraph, HumanScores, Difficulty
├── commands/
│   ├── stats.py           # Dataset coverage display (Rich panels/tables)
│   ├── add.py             # Interactive entry creation (questionary prompts)
│   ├── translate.py       # Translation practice game loop with scoring
│   └── export.py          # Export dataset + results to JSON for dashboard
├── scoring/
│   ├── elo.py             # Elo rating calculations for model comparison
│   └── xp.py              # XP tracking per user (translate=10, add=15, judge=5)
├── providers/             # LLM API wrappers (future)
│   └── __init__.py
└── utils/
    ├── dataset.py         # Load/save JSON data, config, domains, targets
    └── display.py         # Rich console singleton
```

## Key Files by Task

| Task | File |
|---|---|
| Add a new CLI command | `cli.py` (register) + `commands/yourcommand.py` |
| Data models / validation | `models.py` |
| Load/save dataset | `utils/dataset.py` |
| Scoring logic | `scoring/elo.py`, `scoring/xp.py` |
| Config (domains, targets) | `config.yaml` |
| Tests | `tests/` |

---

## Critical Constraints

❌ **Don't break Pydantic models** — `Term`, `Sentence`, `Paragraph` are the source of truth for JSON schema. Changing field names/types requires updating all data files.
❌ **Don't hardcode language** — the CLI reads language pair, domains, and targets from `config.yaml`. Keep code language-agnostic.
❌ **Don't use SQLite** — data is stored as JSON files in `data/`. This is intentional for git-friendliness and transparency.
❌ **Don't import from `data/`** — canonical models live in `src/qebench/models.py`, not in the data directory.

---

## Developer Workflow

### Running Tests

```bash
uv run pytest tests/ -v           # All tests
uv run pytest tests/ -v -k test_xp  # Single test file pattern
uv run pytest tests/ --cov        # Coverage
```

### Code Style

```bash
uv run ruff check src/ tests/
uv run ruff format src/ tests/
```

### Build and Run

```bash
uv sync                           # Install dependencies
uv run qebench --help             # Run CLI
uv run qebench stats              # Example command
```

### Branch & PR Process

- Always work on a branch, never commit directly to `main`
- Use PRs for all changes, including docs
- **Always use create/edit file tools** for file content — never heredoc or shell string escaping
- Multi-line commit messages: write to `.tmp/` first, then use `-F`:
  ```bash
  git commit -F .tmp/msg.txt
  ```

### Using the `gh` CLI

Write output to the local **`.tmp/`** folder (not `/tmp/`) to keep work repo-scoped:

```bash
gh pr view 123 > .tmp/pr.txt && cat .tmp/pr.txt
gh pr create --title "..." --body-file .tmp/pr-body.txt --base main
```

The `.tmp/` folder contents are git-ignored.

---

## Data Layout

```
data/
├── terms/*.json        # Term entries grouped by domain (314 seeded)
├── sentences/*.json    # Sentence entries grouped by domain
└── paragraphs/*.json   # Paragraph entries grouped by domain

results/
├── translations/       # User translation attempts (JSONL per user)
├── xp/                 # XP totals per user (JSON per user)
└── elo.json            # Model Elo ratings (future)
```

JSON files use bare arrays. The loader also supports `{version, entries}` wrapper format.

### Adding a New Command

1. Create `src/qebench/commands/yourcommand.py` with a plain function
2. Register in `cli.py` via `app.command("name", help="...")(fn)` or `@app.command()`
3. Add tests in `tests/test_yourcommand.py`
4. Document in `docs/user/cli-reference.md`

### Pattern: ID Generation

Entry IDs follow `{prefix}-{NNN}` format (e.g. `term-001`, `sent-042`). Use `_next_id(prefix, existing)` from `commands/add.py` to auto-generate the next sequential ID.

### Pattern: Scoring

Character-level Jaccard overlap (`_char_overlap` in `translate.py`) is used for quick feedback. Neural metrics (BLEU, COMET) are Phase 2.

---

## Documentation

Docs use MyST and deploy to GitHub Pages via the `docs.yml` workflow.

```bash
cd docs && myst build --html      # Local build
```

- `docs/user/` — getting-started, cli-reference, tutorials
- `docs/developer/` — architecture, data-models, contributing
- `docs/index.md` — table of contents

---

## Testing Conventions

- Tests live in `tests/` with `test_*.py` naming
- Use `pytest` fixtures for temp directories and monkeypatching
- Test pure logic (scoring, overlap, ID generation) without mocking interactive prompts
- Use `tmp_path` + `monkeypatch` to override file paths in tests
