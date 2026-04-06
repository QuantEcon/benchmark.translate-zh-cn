# Changelog

All notable changes to `qebench` will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.3.1] - 2026-04-07

### Added

- **Duplicate detection in `qebench add`** (PR #19): After entering English text, the command checks all existing entries of the same type for case-insensitive, whitespace-normalised matches. If duplicates are found, shows existing entry details and asks "Add anyway?" (default: No). Prevents accidental duplicates while allowing intentional ones.

### Fixed

- Rich markup injection in duplicate warning — user-content fields are now escaped via `rich.markup.escape`
- Documentation updates for v0.3.0 (PR #18): refreshed model names, added "Neither" judge option, updated seed counts and difficulty rubric

### Changed

- Tests: 213 → 218 (5 new duplicate detection tests)

## [0.3.0] - 2026-04-06

### Added

- **Judge UX improvements** (PR #14 — issues #6, #9, #7):
  - "Neither" option in head-to-head judging when neither translation is acceptable
  - Auto-skip identical translation pairs to avoid wasted comparisons
  - Numeric `rawselect` prompts replace arrow-key selection for better terminal compatibility
- **Difficulty classification** (PR #15 — issue #11):
  - All 314 seed terms classified as basic / intermediate / advanced using education-level rubric (basic = high school, intermediate = undergraduate, advanced = graduate)
  - Distribution: 64 basic (20%), 172 intermediate (55%), 78 advanced (25%)
  - `scripts/classify_difficulty.py` for reproducible classification
- **100% context coverage** (PR #16 — issue #10):
  - Fuzzy matching fallback in context extraction — matches terms where all significant words appear in a paragraph
  - 36 curated context sentences for terms not found in lecture repos
  - `scripts/add_missing_contexts.py` for adding curated contexts
  - Expanded stop-word list and word-boundary-aware pattern matching
- **Pre-populated model outputs** (PR #17 — issue #12):
  - 1,256 Claude translations across 4 model×prompt combinations (Sonnet 4, Haiku 4.5 × default, academic)
  - Concurrent batch translation with `ThreadPoolExecutor` (10 workers) and progress bar
  - Updated model defaults: Claude Sonnet 4 (`claude-sonnet-4-6`), Haiku 4.5 (`claude-haiku-4-5-20251001`)
  - Updated OpenAI defaults: GPT-5.4 (`gpt-5.4`), GPT-5.4 mini (`gpt-5.4-mini`)
  - Legacy model pricing preserved with deprecation warnings for unknown models

### Fixed

- **Submit command** (PR #13 — issue #8): Stage files before `git pull --rebase` to prevent data loss when there are local changes
- `record_judgment` accepts `None` scores for auto-skip, tie, and neither outcomes
- Thread-safe `on_complete` callback — invoked from main thread instead of worker threads

### Changed

- Tests: 206 → 213 (7 new across PRs #13–#17)

## [0.2.1] - 2026-04-02

### Fixed

- **Context extraction rewritten to paragraph-based approach**: QuantEcon lectures use single-sentence paragraphs, so context extraction now splits on blank lines instead of regex-based sentence splitting. This eliminates long multi-sentence/multi-paragraph context entries (the worst was 5,769 chars). All contexts are now capped at 300 chars.
- Removed `_split_sentences()` and `_extract_prose()` in favour of `_extract_paragraphs()` which returns one entry per blank-line-delimited prose block
- Re-enriched all 280 terms with clean, single-sentence contexts from lecture repos

### Changed

- Tests: 207 → 206 (removed regex sentence-splitting tests, added paragraph extraction tests)

## [0.2.0] - 2026-04-02

### Added

- **Phase 3 — LLM provider integration** (PR #3):
  - `qebench run`: Batch LLM translation with provider selection (`--provider claude|openai`)
  - Provider abstraction layer (`providers/base.py`) with Claude and OpenAI implementations
  - Structured prompt templates (`providers/prompts.py`) for term/sentence/paragraph translation
  - 30 new tests (providers, prompts, run command)
- **Phase 4 — Judge mode & Elo ratings** (PR #4):
  - `qebench judge`: Side-by-side comparison of human vs LLM translations with LLM-as-judge
  - Glossary compliance scoring (`scoring/glossary.py`) — checks translations against the official glossary
  - Judgments persistence (`scoring/judgments.py`) — Elo rating updates, per-pair tracking
  - 32 new tests (judge, glossary scoring, judgments)
- **Context sentence enrichment** (PR #5):
  - `qebench update` now clones/updates 4 QuantEcon lecture repos into `.cache/lectures/` and extracts up to 5 usage sentences per term
  - `TermContext` model (`text`, `source`) for contextual usage sentences; `Term.contexts` field holds up to 5 per term
  - `qebench translate` shows a random context sentence alongside terms to help translators understand usage
  - New tutorial: [Updating Datasets](docs/user/tutorials/updating-datasets.md)
  - 45 new tests (context extraction, enrichment, model validation)

### Fixed

- `_enrich_term_contexts()` only rewrites seed files containing enriched terms (not all files)
- Wrapper format (`{version, entries}`) is preserved when writing back enriched terms
- Context selection is deterministic (sorted, first N) to avoid VCS churn; randomness is only at display time
- Multi-line `$$...$$` math blocks properly skipped during prose extraction
- Rich markup in context sentences is escaped to prevent broken rendering

### Changed

- Tests: 109 → 207 (98 new across 3 PRs)

## [0.1.1] - 2026-03-30

### Added

- **`qebench validate`**: Schema validation for all dataset JSON files against Pydantic models — exits non-zero on failure, suitable for CI
- **XP leaderboard** in `qebench stats`: Ranked table with user/XP/translate/add/judge breakdown
- **CI workflow** (`.github/workflows/ci.yml`): Runs `qebench validate` → pytest → ruff on every push and PR

### Fixed

- Defensive JSON parsing in `validate` — handles non-list/non-dict top-level types and non-dict entries without crashing
- `stats` leaderboard guards against corrupted XP files (catches `JSONDecodeError`/`OSError`)
- `Difficulty` enum modernized to `StrEnum` (Python 3.11+)
- Resolved 98 ruff lint errors (unused imports, line length, ambiguous variable names)
- CI installs dev extras (`uv sync --extra dev`) so pytest and ruff are available

### Changed

- Ruff line-length set to 120 in `pyproject.toml`
- Tests: 98 → 109 (added 7 validate + 4 stats tests)

## [0.1.0] - 2026-03-30

First release — ready for RA testing.

### Added

- **CLI commands**: `update`, `stats`, `translate`, `add`, `submit`, `doctor`, `export`
- **Data layer**: Pydantic models (`Term`, `Sentence`, `Paragraph`), JSON dataset loading/saving
- **Seed data**: 314 terms across 15 domains from the QuantEcon glossary
- **Translation collection** (`qebench translate`):
  - Interactive game loop with confidence rating (1–5)
  - Character-overlap similarity scoring (informational, not a grade)
  - Structured diff-reason prompts when translations diverge (formal/informal register, regional, contextual, abbreviation, alt-technical, other)
  - Optional notes field for additional context
- **Entry contribution** (`qebench add`): Interactive prompts for terms, sentences, paragraphs
- **Version tracking**: `cli_version` stamped in every translation record and contributed entry for future schema migration
- **XP system**: 10/translate, 15/add, 5/judge — per-user tracking
- **Elo rating engine**: For future model comparison (Phase 4)
- **GitHub identity**: Auto-detect username via `gh api user`, cached per session
- **Per-user data files**: Eliminates merge conflicts between concurrent contributors
- **`qebench submit`**: Single `git pull --rebase` → commit → push workflow
- **`qebench update`**: Pull latest code + data, sync dependencies
- **`qebench doctor`**: 8 preflight checks (gh, git, auth, remote, config, data, uv)
- **Dashboard**: Chart.js page with coverage stats, domain chart, difficulty doughnut, leaderboard, activity feed, sample browse
- **`qebench export`**: 6 JSON files for dashboard, runs in CI on push
- **Documentation**: MyST-based, 10 pages — getting started, uv guide, CLI reference, tutorials, architecture, data models, contributing
- **Tests**: 98 pytest tests across 12 test files

[0.2.1]: https://github.com/QuantEcon/benchmark.translate-zh-cn/releases/tag/v0.2.1
[0.2.0]: https://github.com/QuantEcon/benchmark.translate-zh-cn/releases/tag/v0.2.0
[0.1.1]: https://github.com/QuantEcon/benchmark.translate-zh-cn/releases/tag/v0.1.1
[0.1.0]: https://github.com/QuantEcon/benchmark.translate-zh-cn/releases/tag/v0.1.0
