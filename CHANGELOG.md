# Changelog

All notable changes to `qebench` will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.5.0] - 2026-04-10

### Added

- **Design review** (`REVIEW.md`): Comprehensive gap analysis of `benchmark.translate-zh-cn` and `action-translation`, with prioritized recommendations.
- **Glossary URL loading** (PR #26): `load_glossary()` in `utils/dataset.py` fetches glossary from GitHub URL (configured in `config.yaml` as `glossary_path`) with local `.cache/glossary.json` fallback. Wired into `qebench run` via optional `{glossary}` prompt placeholder.
- **MyST formatting validators** (PR #26): New `scoring/formatting.py` module with automated checks — directive balance, fence consistency, code block integrity, fullwidth punctuation compliance, directive spacing. Results displayed in `qebench judge` reveal panel.
- **Seed sentences from lectures** (PR #26): 80 curated sentence pairs (8 per domain, 10 domains) extracted from aligned English/Chinese lecture repos via `scripts/seed_from_lectures.py`.
- **Seed paragraphs from lectures** (PR #26): 17 curated paragraph pairs with math, code, directives, and roles. Paragraphs include MyST feature flags for formatting validation.
- **Paragraph model flags** (PR #26): `contains_directives`, `contains_roles`, `contains_mixed_fencing` fields on the `Paragraph` model.
- **Action-translation prompt templates** (PR #26): `prompts/action-basic.txt` (MyST-aware rules) and `prompts/action-new.txt` (MyST rules + glossary injection).
- **Optional `{glossary}` placeholder** in prompt templates (PR #26): Auto-populated from `action-translation`'s glossary when present. Double-brace escaping (`{{math}}`) supported.
- **Formatting scores in judge reveal** (PR #26): After picking a winner, judges see fullwidth punctuation % and directive balance status for both translations.
- **New tutorials**: [Glossary & Prompt Templates](docs/user/tutorials/glossary-and-prompts.md), [Seeding from Lectures](docs/developer/seeding-from-lectures.md).

### Changed

- `config.yaml`: `glossary_path` updated from `null` to `https://raw.githubusercontent.com/QuantEcon/action-translation/main/glossary/zh-cn.json`
- `qebench translate` excludes paragraphs from the entry pool (CLI single-line input limitation); paragraphs remain in `judge` and `run`
- Documentation updated: README, CLI reference, architecture, data models, contributing guide, all affected tutorials
- Tests: 225 → 262 (37 new: 26 formatting, 10 glossary, 1 model)

## [0.4.0] - 2026-04-07

### Added

- **Consensus rating for unanimous translations** (PR #23): When all models agree on a translation, judges rate accuracy and fluency on a 0-5 scale instead of auto-skipping. Optional suggestion prompt when score ≤ 2. Consensus records stored as `type: "consensus"` in judgment JSONL.
- **Context sentences in judge view** (PR #24): First context sentence from `Term.contexts` shown in the source panel so judges have disambiguation info.
- **Suggestion prompt on "Neither"** (PR #24): When a judge picks "Neither — both are poor", they can suggest a better translation. Stored in judgment record.
- **Balanced matchup ordering** (PR #24): Disagreement and consensus matchups are interleaved so judges get a mix instead of mostly consensus rounds.

### Fixed

- **Judge auto-ties from prompt collisions** (PR #22): `_load_model_outputs` now keys by `model:prompt_template` instead of `model` alone, correctly distinguishing 4 model×prompt combos instead of merging them into 2.
- **Update command fails with dirty workdir** (PR #21): Added `--autostash` to `git pull --rebase` in the update command, matching submit command behavior.
- **Tutorial accuracy** (PR #20): Fixed 5 issues across 3 tutorial files for RA onboarding accuracy.
- **Keyboard shortcuts in judge** (PR #24): Switched from `rawselect` to `select` with `use_shortcuts=True` — supports both arrow keys and keyboard shortcuts. Score shortcuts match actual values (0-5) instead of 1-indexed offset. Winner shortcuts: a/b/t/n.
- **Rich markup escape** (PR #24): Context text and entry names escaped with `rich.markup.escape()` to prevent `MarkupError` from dataset content containing `[` or `]`.

### Changed

- Scoring scale changed from 1-10 to 0-5 for accuracy and fluency
- Tests: 218 → 225

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
