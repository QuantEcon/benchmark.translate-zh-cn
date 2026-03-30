# Architecture

## Overview

`qebench` is a Python CLI tool built on three layers:

```
┌─────────────────────────────────────┐
│          CLI Commands               │  ← Typer commands (translate, add, stats)
├─────────────────────────────────────┤
│     Scoring    │    Providers       │  ← Elo, XP, glossary │ Claude, OpenAI
├─────────────────────────────────────┤
│     Data Layer (models + utils)     │  ← Pydantic models, JSON I/O
└─────────────────────────────────────┘
```

## Module Map

```
src/qebench/
├── cli.py                 # Typer app — 6 commands: stats, add, translate, export, submit, doctor
├── models.py              # Pydantic models: Term, Sentence, Paragraph, DataFile
├── commands/
│   ├── stats.py           # Dataset coverage display (Rich panels/tables)
│   ├── add.py             # Interactive entry creation → saves to per-user file
│   ├── translate.py       # Translation practice game loop
│   ├── export.py          # Export 6 JSON files for the dashboard
│   ├── submit.py          # Git pull/commit/push workflow
│   └── doctor.py          # 8 preflight checks (gh, git, repo, data, etc.)
├── scoring/
│   ├── elo.py             # Elo rating for model comparison
│   └── xp.py              # XP tracking per user
├── providers/             # LLM API wrappers (Phase 3)
│   └── __init__.py
└── utils/
    ├── dataset.py         # Load/save JSON data, config, domain list
    ├── display.py         # Rich console singleton
    └── github.py          # get_github_username() via gh CLI (cached)
```

## Data Flow

### Translation Session
```
User runs: qebench translate -n 5
    │
    ▼
github.py ──→ auto-detects username via `gh api user`
    │
    ▼
dataset.py ──→ loads terms/sentences/paragraphs from data/**/*.json
    │           (merges _seed_*.json + per-user files)
    ▼
translate.py ──→ picks entries, presents English, collects Chinese
    │
    ├──→ _char_overlap() ──→ scores attempt vs reference
    ├──→ _save_attempt() ──→ appends to results/translations/{username}.jsonl
    └──→ xp.award_xp()  ──→ updates results/xp/{username}.json
```

### Add Entry
```
User runs: qebench add
    │
    ▼
add.py ──→ questionary prompts for entry type + fields
    │
    ▼
models.py ──→ validates entry via Pydantic
    │
    ▼
add.py ──→ _save_to_user_file() ──→ appends to data/terms/{username}.json
```

### Submit Results
```
User runs: qebench submit
    │
    ▼
submit.py ──→ git pull --rebase
    │       ──→ git add data/ results/
    │       ──→ git commit -m "benchmark: add data ..."
    │       ──→ git push
    ▼
Dashboard CI rebuilds automatically on push
```

### Export & Dashboard
```
User (or CI) runs: qebench export
    │
    ▼
export.py ──→ loads all data + results
    │       ──→ computes coverage, domain stats, difficulty stats,
    │           leaderboard, activity feed, term samples
    │       ──→ writes 6 JSON files to docs/_static/dashboard/data/
    ▼
MyST build + gh-pages deploys the dashboard
```

## Key Design Decisions

### JSON files over SQLite
Git-friendly, transparent, easy for RAs to inspect and edit manually. Per-user
files avoid merge conflicts when multiple RAs work simultaneously.

### Per-user data files
Each contributor gets their own file (`data/terms/{username}.json`). Seed data
uses the `_seed_` prefix (`data/terms/_seed_economics.json`). All files are
loaded together at runtime via glob — the distinction is purely organizational.

### GitHub identity via `gh` CLI
Username auto-detected with `gh api user --jq .login` (cached with `lru_cache`).
No manual `--user` flags needed. Requires `gh auth login` as a one-time setup.

### Pydantic for schemas
Type safety + auto JSON Schema generation + validation in one place. Models serve
double duty as the validation layer and the documentation of the data format.

### Character-level overlap for scoring
Simple Jaccard similarity on Chinese character sets. Not linguistically
sophisticated, but fast, deterministic, and good enough for feedback during
practice sessions. Neural metrics (BLEU, COMET) come in Phase 2.

### XP stored per-user in JSON
Each user gets a separate file (`results/xp/{username}.json`). Avoids write
conflicts when multiple RAs work simultaneously. Aggregation happens at display
time.

### Recursive `add()` for "add another"
The `add` command calls itself recursively to allow adding multiple entries in
one session without restarting. Simple and works well for CLI UX.

## Directory Layout

```
benchmark.translate-zh-cn/
├── data/
│   ├── terms/
│   │   ├── _seed_economics.json   # Seeded terms (read-only, by domain)
│   │   ├── _seed_mathematics.json
│   │   ├── ...                    # 15 seed files total, 314 terms
│   │   └── {username}.json        # Per-user contributions
│   ├── sentences/*.json           # Sentence entries (same pattern)
│   └── paragraphs/*.json          # Paragraph entries (same pattern)
├── results/
│   ├── translations/              # User translation attempts (JSONL per user)
│   ├── xp/                        # XP totals per user (JSON per user)
│   └── elo.json                   # Model Elo ratings (future)
├── docs/
│   ├── _static/dashboard/         # Chart.js dashboard + exported JSON
│   └── ...                        # MyST documentation
├── config.yaml                    # Language pair, domains, targets
└── src/qebench/                   # Python package (see Module Map above)
```

## Configuration

All language-specific settings live in `config.yaml`:

```yaml
language_pair:
  source: en
  target: zh-cn

domains:
  - economics
  - mathematics
  - statistics
  # ...

targets:
  terms: 500
  sentences: 100
  paragraphs: 30
```

The CLI code is language-agnostic — it reads domain lists and targets from
config at runtime. This makes it possible to extract the tool for other
language pairs later.
