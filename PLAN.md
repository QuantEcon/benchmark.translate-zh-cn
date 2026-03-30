# Infrastructure Plan

> Internal document for building the `benchmark.translate-zh-cn` infrastructure.
> The RA-facing project description lives in `action-translation/docs/projects/PROJECT-A-BENCHMARK.md`.

## Architecture Overview

Three components that work together:

1. **Data layer** — Pydantic models, JSON Schema validation, dataset loading/saving
2. **CLI tool (`qebench`)** — Typer-based CLI with interactive modes (translate, judge, add, run, stats, export)
3. **Results website** — Static GitHub Pages site generated from JSON results

Data flows: `qebench add/translate/judge` → `results/*.json` → `qebench submit` → GitHub → `qebench export` (CI) → `dashboard/data/` → GitHub Pages.

## Identity & Data Model

RAs authenticate via GitHub CLI (`gh auth login`). Username is auto-detected via `gh api user`.

All user-generated files are per-user to eliminate merge conflicts:
- `data/terms/{username}.json` — terms contributed by each user
- `data/terms/_seed_*.json` — initial seeded data (read-only)
- `results/xp/{username}.json` — XP tracking
- `results/translations/{username}.jsonl` — translation attempts

The `qebench submit` command handles the full git ceremony (pull --rebase → add → commit → push). RAs push directly to `main` — per-user files prevent conflicts.

## Versioning & Schema Migration

RAs always run from `main` (no separate release installs). `qebench update` pulls latest code + data, then syncs dependencies. Tests protect `main` on every push.

Every data record (`translate` JSONL lines, `add` JSON entries) includes a `cli_version` field stamped at write time. If the data schema changes in a future release, this field provides a migration path — we can identify which records were written by which version and transform them accordingly.

Releases are tagged (`v0.1.0`, etc.) as milestones for the CHANGELOG. See [CHANGELOG.md](CHANGELOG.md).

## Technology Stack

| Role | Library | Version | Why |
|---|---|---|---|
| CLI framework | [Typer](https://typer.tiangolo.com/) | 0.24+ | Type-hint driven, auto help/completion, built on Click |
| Terminal UI | [Rich](https://rich.readthedocs.io/) | 14+ | Panels, tables, progress bars, styled text |
| Interactive prompts | [questionary](https://questionary.readthedocs.io/) | 2.1+ | Select, input, confirm — mature, 20k+ dependents |
| Data validation | [Pydantic](https://docs.pydantic.dev/) | 2.x | Type-safe models, auto JSON Schema generation |
| LLM: Anthropic | [anthropic](https://docs.anthropic.com/) | 0.40+ | First-class Python SDK |
| LLM: OpenAI | [openai](https://platform.openai.com/docs/) | 1.x | First-class Python SDK |
| Testing | [pytest](https://pytest.org/) | 8+ | Standard Python test framework |
| Package mgmt | [uv](https://docs.astral.sh/uv/) | latest | Fast, modern Python packaging |
| Site charts | [Chart.js](https://www.chartjs.org/) | 4.x | Elo trends, coverage progress, leaderboard |

## Repository Structure

```
benchmark.translate-zh-cn/
├── data/
│   ├── terms/                        # Term-level translation pairs (JSON)
│   │   ├── economics.json
│   │   ├── mathematics.json
│   │   └── statistics.json
│   ├── sentences/                    # Sentence-level pairs
│   │   ├── definitions.json
│   │   └── theorems.json
│   ├── paragraphs/                   # Paragraph-level pairs
│   │   └── quantecon-extracts.json
│   └── schema/
│       └── models.py                 # Pydantic models → auto JSON Schema
├── src/
│   └── qebench/                      # Python package
│       ├── __init__.py
│       ├── cli.py                    # Typer app — command routing
│       ├── commands/
│       │   ├── __init__.py
│       │   ├── translate.py          # "translate" mode
│       │   ├── judge.py              # "judge" mode
│       │   ├── add.py                # "add" mode
│       │   ├── run.py                # benchmark runner
│       │   ├── stats.py              # stats display (Rich tables/panels)
│       │   └── export.py             # export for website
│       ├── providers/                # LLM API wrappers
│       │   ├── __init__.py
│       │   ├── base.py               # Abstract provider interface
│       │   ├── claude.py             # Anthropic SDK
│       │   ├── openai.py             # OpenAI SDK
│       │   └── local.py              # Ollama/local LLM support
│       ├── scoring/
│       │   ├── __init__.py
│       │   ├── glossary.py           # Glossary compliance check
│       │   ├── elo.py                # Elo rating calculations
│       │   └── xp.py                 # XP calculations
│       └── utils/
│           ├── __init__.py
│           ├── display.py            # Rich console helpers
│           └── dataset.py            # Data loading/saving (Pydantic)
├── tests/
│   ├── conftest.py
│   ├── test_dataset.py
│   ├── test_scoring.py
│   └── test_providers.py
├── results/
│   ├── translations/                 # Human translations from "translate" mode
│   ├── judgments/                     # Ratings from "judge" mode
│   ├── model-outputs/                # LLM benchmark outputs
│   ├── elo.json                      # Running Elo ratings
│   ├── leaderboard.json              # XP and contribution stats
│   └── weekly.json                   # Translation of the week picks
├── prompts/                          # Prompt variations for A/B testing
│   ├── default.txt
│   └── ...
├── site/                             # GitHub Pages website
│   ├── index.html
│   ├── leaderboard.html
│   ├── models.html
│   ├── coverage.html
│   ├── weekly.html
│   ├── browse.html
│   ├── css/
│   ├── js/
│   └── data/                         # Generated JSON (from qebench export)
├── .github/
│   └── workflows/
│       ├── validate.yml              # PR validation (schema check, pytest)
│       └── deploy-site.yml           # Build + deploy site on push
├── config.yaml                       # Language-specific settings
├── PLAN.md                           # This file
├── CONTRIBUTING.md
├── pyproject.toml
└── README.md
```

### Design: Tool vs Data Separation

The CLI code (`src/qebench/`) is language-agnostic by design. Language-specific
configuration (glossary path, language pair, domain list) lives in `config.yaml`.
If the project succeeds, extracting the tool into a standalone `tools-benchmark`
package is straightforward: move `src/qebench/`, keep `data/` here, install the
tool as a dependency.

## Build Order

### Phase 1: Foundation (Layers 1–2)

Everything else depends on having a working data layer.

**Layer 1: Project scaffold**
- [x] Initialize git repo
- [x] Create directory structure
- [x] `pyproject.toml` with dependencies and `[project.scripts]` entry
- [x] `.gitignore` for Python
- [x] `config.yaml` with zh-cn language settings
- [x] README.md

**Layer 2: Data layer**
- [x] Pydantic models: `Term`, `Sentence`, `Paragraph` (in `src/qebench/models.py`)
- [x] Dataset utilities: load/save/filter JSON data (in `src/qebench/utils/dataset.py`)
- [x] Seed script: convert `action-translation/glossary/zh-cn.json` → benchmark format (314 terms seeded)
- [ ] Schema validation script (CI-ready)
- [x] `qebench stats` command — Rich output with progress bars + domain table
- [x] pytest tests for models and dataset loading (23 tests)

### Phase 2: CLI Core (Layer 3)

The interactive modes that make RAs want to contribute.

- [x] `qebench translate` — game loop with char-overlap scoring, domain/difficulty filters, XP tracking
- [x] `qebench add` — interactive entry creation with questionary prompts, preview, auto-ID
- [x] XP tracking system (`src/qebench/scoring/xp.py`) — 10/translate, 15/add, 5/judge
- [x] Elo rating engine (`src/qebench/scoring/elo.py`)
- [x] GitHub identity — auto-detect username via `gh api user`, cached per session
- [x] Per-user data files — `data/terms/{username}.json` (seed data in `_seed_*.json`)
- [x] `qebench submit` — pull --rebase, commit data/ + results/, push to GitHub
- [x] `qebench doctor` — 8 preflight checks (gh, git, auth, remote, config, data, uv)
- [x] `qebench update` — pull latest code + data (`git pull --rebase`) and sync dependencies (`uv sync`)
- [x] Results committed to repo — XP + translations tracked in git, dashboard reads them
- [ ] `qebench stats` — leaderboard display (current: coverage + domain table)
- [x] 98 pytest tests passing (models: 12, dataset: 7, scoring: 6, translate: 21, xp: 11, export: 16, github: 6, submit: 7, doctor: 6, update: 4, add: 2)

### Phase 3: LLM Integration (Layer 4)

Model benchmarking and comparison.

- [ ] Abstract provider interface (`src/qebench/providers/base.py`)
- [ ] Claude provider (Anthropic SDK)
- [ ] OpenAI provider
- [ ] `qebench run` — batch translate dataset entries via selected models
- [ ] Prompt template loading from `prompts/`
- [ ] Rate limiting and cost tracking

### Phase 4: Judge Mode & Elo (Layer 5)

Human evaluation system.

- [x] Elo rating engine (`src/qebench/scoring/elo.py`) — moved to Phase 1
- [ ] `qebench judge` — anonymous head-to-head comparisons
- [ ] Glossary compliance scorer
- [ ] Reference overlap scorer
- [ ] Results persistence (elo.json, judgments/)

### Phase 2.5: Dashboard Website

Standalone dashboard page deployed alongside MyST docs on GitHub Pages.

- [x] `qebench export` — aggregate dataset + results to 6 JSON files (`docs/_static/dashboard/data/`)
- [x] Dashboard HTML page (`docs/_static/dashboard/index.html`) — Chart.js, dark theme
- [x] Stats cards: total entries, terms, sentences, paragraphs with progress bars
- [x] Domain bar chart + difficulty doughnut chart
- [x] Leaderboard table (XP + action breakdown)
- [x] Activity feed (recent translation attempts, color-coded scores)
- [x] Sample terms browse grid
- [x] Workflow updated: Python+uv export → MyST build → copy dashboard → deploy pages
- [x] 16 pytest tests for export (domain stats, difficulty, XP leaderboard, activity feed, samples, integration)
- [x] Dashboard link in docs sidebar and index page

### Phase 5: Extended Website (Layer 6)

Extended pages beyond the dashboard.

- [ ] Model comparison page (requires Phase 3 LLM data)
- [ ] Coverage map visualization
- [ ] Translation of the Week picks
- [ ] Browse/search dataset pages
- [ ] GitHub Actions: validate.yml (PR validation, schema check)

### Documentation

Docs hosted on GitHub Pages via MyST.

- [x] `docs/index.md` — documentation index
- [x] User guide: getting-started, cli-reference, tutorials (first-session, contributing-entries)
- [x] Developer guide: architecture, data-models, contributing
- [x] `myst.yml` — MyST build configuration
- [x] `.github/workflows/docs.yml` — auto-deploy to gh-pages
- [x] `AGENTS.md` — Copilot agent instructions

## Data Models

### Term

```python
class Term(BaseModel):
    id: str                          # "term-001"
    en: str                          # "Bellman equation"
    zh: str                          # "贝尔曼方程"
    domain: str                      # "dynamic-programming"
    difficulty: Difficulty           # basic | intermediate | advanced
    alternatives: list[str] = []    # ["贝尔曼等式"]
    source: str = ""                # "quantecon/dp-intro"
```

### Sentence

```python
class Sentence(BaseModel):
    id: str                          # "sent-042"
    en: str
    zh: str
    domain: str
    difficulty: Difficulty
    key_terms: list[str] = []       # ["term-001"]
    human_scores: HumanScores | None = None
    source: str = ""
```

### Paragraph

```python
class Paragraph(BaseModel):
    id: str                          # "para-007"
    en: str
    zh: str
    domain: str
    difficulty: Difficulty
    key_terms: list[str] = []
    contains_math: bool = False
    contains_code: bool = False
    human_scores: HumanScores | None = None
    source: str = ""
```

### Config

```yaml
# config.yaml
language_pair:
  source: en
  target: zh-cn

glossary_path: ../action-translation/glossary/zh-cn.json

domains:
  - economics
  - macroeconomics
  - microeconomics
  - dynamic-programming
  - mathematics
  - linear-algebra
  - statistics
  - probability
  - finance
  - game-theory
  - optimization

targets:
  terms: 500
  sentences: 100
  paragraphs: 30
```

## Scoring System

### Phase 1 (Semester): Human + Simple Automated

| Metric | Implementation | Module |
|---|---|---|
| Glossary compliance | Exact match against term dictionary | `scoring/glossary.py` |
| Reference overlap | Character-level similarity (Jaccard on characters) | `scoring/glossary.py` |
| Elo rating | Standard Elo from head-to-head judgments | `scoring/elo.py` |
| Human accuracy | 1-10 score from judge mode | stored in judgments JSON |
| Human fluency | 1-10 score from judge mode | stored in judgments JSON |
| XP | Action-based points (translate=10, add=15, judge=5) | `scoring/xp.py` |

### Phase 2 (Summer): Neural Metrics

| Metric | Package | Notes |
|---|---|---|
| BLEU | `sacrebleu` | Standard MT baseline |
| COMET | `unbabel-comet` | Best correlation with human scores |
| XCOMET | `unbabel-comet` | COMET + error span identification |

## Key Design Decisions

1. **Python over TypeScript** — richer CLI ecosystem (Typer+Rich+questionary), RA familiarity, no build step, native COMET/BLEU support for summer phase
2. **Single repo first** — avoid premature abstraction; extract `tools-benchmark` after proving the concept
3. **JSON files over SQLite** — git-friendly, transparent, easy for RAs to inspect and edit
4. **Pydantic for schemas** — type safety + auto JSON Schema generation + validation in one place
5. **uv for packaging** — fast, handles Python versions, replaces pip+venv+pip-tools
6. **config.yaml for language settings** — keeps tool code language-agnostic from day one
