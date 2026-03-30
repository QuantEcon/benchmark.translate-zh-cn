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
├── cli.py                 # Typer app — command routing + argument parsing
├── models.py              # Pydantic models: Term, Sentence, Paragraph
├── commands/
│   ├── stats.py           # Dataset coverage display (Rich panels/tables)
│   ├── add.py             # Interactive entry creation (questionary prompts)
│   └── translate.py       # Translation practice game loop
├── scoring/
│   ├── elo.py             # Elo rating for model comparison
│   └── xp.py              # XP tracking per user
├── providers/             # LLM API wrappers (Phase 3)
│   └── __init__.py
└── utils/
    ├── dataset.py         # Load/save JSON data, config, domain list
    └── display.py         # Rich console singleton
```

## Data Flow

### Translation Session
```
User runs: qebench translate -n 5 -u alice
    │
    ▼
dataset.py ──→ loads terms/sentences/paragraphs from data/*.json
    │
    ▼
translate.py ──→ picks entries, presents English, collects Chinese
    │
    ├──→ _char_overlap() ──→ scores attempt vs reference
    ├──→ _save_attempt() ──→ appends to results/translations/alice.jsonl
    └──→ xp.award_xp()  ──→ updates results/xp/alice.json
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
add.py ──→ _save_to_domain_file() ──→ appends to data/{type}/{domain}.json
```

## Key Design Decisions

### JSON files over SQLite
Git-friendly, transparent, easy for RAs to inspect and edit manually. Each domain
gets its own file so merge conflicts are rare.

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
│   ├── terms/*.json       # Term entries grouped by domain
│   ├── sentences/*.json   # Sentence entries grouped by domain
│   └── paragraphs/*.json  # Paragraph entries grouped by domain
├── results/
│   ├── translations/      # User translation attempts (JSONL per user)
│   ├── xp/                # XP totals per user (JSON per user)
│   └── elo.json           # Model Elo ratings (future)
├── config.yaml            # Language pair, domains, targets
└── src/qebench/           # Python package (see Module Map above)
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
