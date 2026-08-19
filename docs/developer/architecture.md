# Architecture

## Overview

`qebench` is a Python CLI tool built on three layers:

```
┌─────────────────────────────────────┐
│          CLI Commands               │  ← Typer commands (translate, add, stats)
├─────────────────────────────────────┤
│     Scoring    │    Providers       │  ← Elo, ratings, alignment, XP, glossary │ Claude, OpenAI
├─────────────────────────────────────┤
│     Data Layer (models + utils)     │  ← Pydantic models, JSON I/O
└─────────────────────────────────────┘
```

## Module Map

```
src/qebench/
├── cli.py                 # Typer app — 10 commands: stats, add, translate, export, submit, doctor, update, validate, run, judge
├── models.py              # Pydantic models: Term, Sentence, Paragraph, DataFile
├── commands/
│   ├── stats.py           # Dataset coverage + XP leaderboard (Rich panels/tables)
│   ├── add.py             # Interactive entry creation → saves to per-user file
│   ├── translate.py       # Translation practice game loop
│   ├── export.py          # Export 7 JSON files for the dashboard
│   ├── submit.py          # Git pull/commit/push workflow
│   ├── doctor.py          # 8 preflight checks (gh, git, repo, data, etc.)
│   ├── update.py          # Pull latest code + uv sync dependencies
│   ├── validate.py        # Schema validation + en/zh alignment check (--strict fails on warnings)
│   ├── run.py             # Batch translate via LLM providers
│   └── judge.py           # Anonymous head-to-head translation judging
├── scoring/
│   ├── alignment.py       # The en/zh alignment rule — shared by the seeder, the audit script, and validate
│   ├── elo.py             # Elo rating for model comparison
│   ├── formatting.py      # MyST formatting fidelity checks (directive balance, punctuation, etc.)
│   ├── glossary.py        # Glossary compliance + reference overlap scoring
│   ├── judgments.py       # Judgment persistence + Elo update orchestration
│   ├── ratings.py         # Replays committed judgment logs into model ratings
│   └── xp.py              # XP tracking per user
├── providers/
│   ├── base.py            # Abstract TranslationProvider + TranslationResult
│   ├── claude.py          # Anthropic Claude provider
│   ├── openai.py          # OpenAI provider
│   └── prompts.py         # Prompt template loading/validation (supports {glossary} placeholder)
└── utils/
    ├── context.py         # Context-sentence extraction from cloned lecture repos (used by update.py)
    ├── dataset.py         # Load/save JSON data, config, domain list, glossary loading
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
    │           (drops entries this user already attempted, then weights
    │            the draw towards entries one attempt short of consensus;
    │            --uniform opts out)
    │
    ├──→ confidence prompt ──→ 1–5 rating of translator certainty
    ├──→ notes prompt      ──→ optional context / reasoning
    ├──→ _reference_panel() ─→ shows reference (educational, no score)
    ├──→ _save_attempt()   ──→ appends to results/translations/{username}.jsonl
    │                        (includes cli_version for schema migration)
    └──→ xp.award_xp()    ──→ updates results/xp/{username}.json
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
    │       ──→ ratings.py replays results/judgments/*.jsonl into
    │           model ratings (results/elo.json is a gitignored cache,
    │           so the committed logs are the source of truth)
    │       ──→ writes 7 JSON files to docs/_static/dashboard/data/
    ▼
MyST build + gh-pages deploys the dashboard
```

## Scoring Module

### Formatting Fidelity (`scoring/formatting.py`)

Automated checks that verify structural integrity of LLM translations.
`qebench judge` invokes them and displays the result in the reveal panel;
`qebench run` stamps the same `formatting_score()` dict onto every output
record it writes.

| Function | Returns | What it checks |
|---|---|---|
| `check_directive_balance(source, translated)` | `bool` | Fence count (```) matches between source and translation |
| `check_fence_consistency(translated)` | `bool` | No mixed `$$` / `` ```{math} `` markers |
| `check_code_block_integrity(source, translated)` | `bool` | Code blocks preserved verbatim |
| `check_fullwidth_punctuation(text)` | `float` | Fraction (0–1) of punctuation that is fullwidth (，。！？) |
| `check_directive_spacing(text)` | `float` | Fraction (0–1) of CJK→directive boundaries with proper spacing |
| `formatting_score(source, translated)` | `dict` | Runs all checks, returns per-check results |

Helper functions:
- `_extract_code_blocks(text)` — extracts fenced code blocks from markdown
- `_strip_code_and_math(text)` — removes code and math blocks before punctuation analysis

### En/zh Alignment (`scoring/alignment.py`)

The single definition of what makes a seeded en/zh pair sound — a `zh` that
is not a translation of its `en` quietly teaches judges from the wrong text.
`check_pair(en, zh)` returns a list of problems (empty when the pair looks
sound) from three signals a faithful translation preserves: math spans,
`{doc}`/`{eq}`/`{ref}` reference targets, and length ratio.

Three callers share it so they cannot drift apart:
`scripts/seed_from_lectures.py` refuses to seed a pair it rejects,
`scripts/audit_alignment.py` reports on the committed dataset, and
`qebench validate` surfaces regressions in CI (warnings by default,
failures under `--strict`). See [Seeding from
Lectures](seeding-from-lectures.md) for the constants.

### Model Ratings (`scoring/ratings.py`)

`results/elo.json` is gitignored and was only ever written incrementally by
whoever happened to be judging, so ratings never left that machine. The
judgment logs under `results/judgments/` are committed, so `ratings.py`
replays *them* instead — which makes the numbers reproducible, lets CI
compute them, and means a lost cache costs nothing.

`recompute_elo(records, by_prompt=...)` ranks `model:prompt` labels when
`by_prompt=True` and bare models when `False`; neither is a superset of the
other, so `qebench export` publishes both in `ratings.json`. Judgments
against `human-reference` are excluded — the reference is not a competitor.

### Glossary Loading (`utils/dataset.py`)

The `load_glossary()` function fetches the glossary from `config.yaml`'s
`glossary_path` (URL or local path):

```
load_glossary(force_refresh=False)
    │
    ├── glossary_path is URL?
    │     ├── Fetch via urllib.request.urlopen()
    │     ├── Cache to .cache/glossary.json
    │     └── On network failure: fall back to cache
    │
    └── glossary_path is local path?
          └── Read directly
    │
    ▼
_extract_glossary_terms(data)
    └── Parses glossary JSON → list[dict] (each dict has en + zh-cn keys)
```

### Prompt Template System (`providers/prompts.py`)

Templates use `{placeholder}` syntax. Required placeholders:
`{source_lang}`, `{target_lang}`, `{domain}`, `{text}`.

Optional placeholder: `{glossary}` — auto-populated from the glossary when
present in a template. Double braces `{{...}}` are treated as literal braces
(e.g., `{{math}}` renders as `{math}` in the final prompt).

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

### Similarity as a trigger, not a grade
Character-level Jaccard similarity (`_char_overlap`) is computed for each
translation, but it's used as an informational metric and a trigger: when
similarity falls below 85%, the user is prompted for *why* their translation
differs (formal/informal register, regional preference, context, abbreviation,
alternative technical term, etc.).  This captures the variation and the
reasoning behind it — the most valuable data for improving the translator.

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
│   ├── sentences/
│   │   ├── _seed_lectures.json    # 80 sentences from lecture repos
│   │   └── {username}.json
│   └── paragraphs/
│       ├── _seed_lectures.json    # 17 paragraphs with math/code/directives
│       └── {username}.json
├── prompts/
│   ├── default.txt                # General-purpose translation prompt
│   ├── academic.txt               # Academic register emphasis
│   ├── action-basic.txt           # MyST-aware rules (no glossary)
│   └── action-new.txt             # MyST-aware rules + glossary injection
├── scripts/
│   ├── seed_from_glossary.py      # Seed terms from action-translation glossary
│   ├── seed_from_lectures.py      # Seed sentences/paragraphs from lecture repos
│   ├── add_missing_contexts.py    # Hand-written context for terms absent from lecture prose
│   ├── classify_difficulty.py     # Auto-classify term difficulty
│   ├── analyze_runs.py            # Aggregate model-output runs into the NOTES.md tables
│   ├── audit_alignment.py         # CLI over scoring/alignment.py — audits committed en/zh pairs
│   └── glossary_syncback.py       # Propose glossary changes back to action-translation
├── results/
│   ├── translations/              # User translation attempts (JSONL per user)
│   ├── model-outputs/             # LLM translations (JSONL per model×prompt)
│   ├── judgments/                 # Judge results (JSONL per user) — source of truth for ratings
│   ├── xp/                        # XP totals per user (JSON per user)
│   ├── glossary-syncback/         # Proposed glossary changes for action-translation
│   └── elo.json                   # Local Elo cache (gitignored; rebuilt by scoring/ratings.py)
├── .cache/
│   ├── glossary.json              # Cached glossary from action-translation
│   └── lectures/                  # Cloned lecture repos (gitignored)
├── docs/
│   ├── _static/dashboard/         # Chart.js dashboard + exported JSON
│   └── ...                        # MyST documentation
├── config.yaml                    # Language pair, domains, targets, glossary URL
├── REVIEW.md                      # Design review & gap analysis
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
