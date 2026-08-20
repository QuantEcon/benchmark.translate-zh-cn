# Changelog

All notable changes to `qebench` will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- **Prompt caching for the shared part of a prompt** (issue #37): Every template ends with `{text}`, so everything before it is identical for each entry in a run. `qebench run` now sends that prefix as its own cacheable content block and the entry as a second block. The prompt text is unchanged — only its packaging. This is aimed at `action-new`, where the injected glossary is about 5,200 of the roughly 5,250 tokens spent per term. Replaying the six committed `action-new` runs against the new billing puts them at **$1.88 rather than $8.86**, and the Sonnet terms run at $0.83 rather than $4.9973. `--no-cache` sends the original single-block prompt.
- **`--cache` / `--no-cache` on `qebench run`**: On by default. `--no-cache` reproduces pre-caching billing, so a cached and an uncached run of the same grid stay comparable.
- **`cache_creation_tokens` and `cache_read_tokens` on every run record**: The three token counts do not overlap — `input_tokens` is what was billed at the full input rate, and the whole prompt is the sum of all three. `scripts/analyze_runs.py` reports the sum in its existing **Input tok** column and adds a **Cached tok** column when any run used the cache, so a cached run stays comparable with the uncached August round. Records written before this release carry neither field and read back as zero, which is the truth for them.
- **13 more paragraphs, 17 → 30** (issue #37): The target in `README.md` is met. Selection now takes paragraphs carrying directives or roles first — those are what `directive_balance` and `directive_spacing` score, and a 100% pass rate over easy prose says little. Directive-carrying entries go from 6/17 to 11/30, math from 12 to 23, code from 6 to 12. No paragraph with mixed fencing exists in the candidate pool, so that part of the ask is unmet rather than partly met. All 30 pass `validate --strict` and the alignment audit flags 0.
- **`--append` on `scripts/seed_from_lectures.py`**: Ids are positional, so the existing behaviour — rewrite the file, renumber every entry — would have detached translation attempts, judgments and the #34 reference repairs from their entries. `--append` keeps every committed entry byte for byte and adds new ones after it. The destructive path now needs `--overwrite` said out loud, and running with neither flag against existing files stops rather than guessing. `--paragraph-target`, `--sentence-target` and `--max-per-domain` replace editing the source to change a target.
- **`providers.base.split_prompt()`**: Renders a template as `(prefix, suffix)` at the `{text}` boundary. `prefix + suffix` is exactly what the un-split `.format()` produced, so a provider that cannot cache concatenates the two and sends the original prompt. The source text is concatenated rather than substituted, so a paragraph containing ```` ```{math} ```` is not re-read as a format field.

### Fixed

- **`scripts/analyze_runs.py` exited 0 when `--dir` did not exist**, so a typo in CI read as a clean run over an empty directory. It now prints the reason and exits 2, and writes no `--json` file. A directory that exists but holds nothing, or holds only corrupt files, still exits 0 — nothing found is not the same failure as nowhere to look.
- **A no-op `--append` could still add an entry.** `_curate_sentences()` appends before it checks the target, so it returned one sentence whenever the target was zero or less — and in `--append` mode the target is the shortfall against what is already committed, making `--sentence-target 80` against 80 committed sentences compute 0 and hand back a candidate. It never landed a row only because the top-scored candidate was already committed and the new dedup pass dropped it; had upstream rewrapped that sentence past the similarity threshold, a no-op run would have appended `sent-081`. Guarded inside the function so it holds for every caller. Re-running `--append` at the default targets is now a true no-op. Found by Copilot's review of PR #38.
- **Near-duplicate seed candidates**: The seeder compared candidates against committed entries on exact text, so a passage upstream had rewrapped or renumbered came back as a second entry. Three of the first thirteen paragraph candidates were re-extractions of `para-001`, `para-016` and `para-007` at 0.95 similarity or better, while nothing unrelated came within 0.50. Comparison is now on whitespace-normalised text plus a 0.90 similarity ratio, with text under 120 characters still needing to match exactly. A test asserts no two committed paragraphs are the same passage.
- **A brace in a glossary entry would have crashed a run.** The glossary is substituted into the template before `str.format()` renders it, so a headword such as `Set {math}` would have been read as a format field. Braces are escaped on injection; the glossary carries none today, across 357 terms. Injection moved into `run._inject_glossary()` so it is testable on its own.

### Changed

- **`translate_batch` warms the cache before it fans out.** A cache entry is only readable once the response that wrote it has begun, so firing all ten workers at once made every one of them pay the 1.25x write premium. One entry per distinct prefix is now translated first. Prefixes are grouped rather than assumed identical because `action-new` interpolates `{domain}` on line 3, **ahead of** the glossary — a terms run renders 15 distinct prefixes, one per domain, not one for the run.
- **A prefix rendered by a single entry is left uncached.** A write costs 1.25x and a read 0.1x, so caching an entry nothing reads back only costs more. Three of the 17 paragraphs are the only entry in their domain.
- `TranslationProvider.translate()` takes `cache_prefix`, which `translate_batch` sets False for those single-entry prefixes. Providers that do not cache prompts ignore it.
- The OpenAI provider reports `prompt_tokens_details.cached_tokens` as `cache_read_tokens` and subtracts it from `input_tokens`, so both providers agree on what the fields mean. Cached tokens are still billed at the full input rate there — OpenAI discounts them, but the rate is not pinned per model in `_PRICING`, so the reported cost is an upper bound until the OpenAI baseline lands.
- Tests: 626 → 706.

### Notes

- **`action-basic`'s failure on short fragments is a framing fault, not a missing glossary** (issue #37). `results/model-outputs/NOTES.md` read the August result — Haiku emitting documentation pages for 42.7% of terms under `action-basic` and 0% under `action-new` — as the glossary block being what holds the model in translation mode. Tested directly over 30 short terms, three lines of scoping (+43 tokens) fix it as completely as the 5,000-token glossary, and so does a 20-term glossary; what they share is showing the model that the expected output is short. The broken prompt is also the expensive one, at about five times the scoped variant, because each failure emits a 450–1,832 token page instead of a nine-token translation. Replicated on a held-out 30. `prompts/action-basic.txt` is **unchanged** — editing it would break comparability with the `action-basic` records already committed. NOTES.md carries the numbers and the recommendation.

### Known

- **Moving `Domain: {domain}` below the glossary in `prompts/action-new.txt` would collapse 15 cache entries into one**, taking the Sonnet terms run from about $0.83 to about $0.55. It is not done here because it changes the prompt, and every `action-new` record already committed was produced with the domain on line 3.

## [0.6.0] - 2026-08-19

A tooling release. The v0.5.0 features — MyST formatting validators, the `action-*` prompts, seeded paragraphs — had no LLM output to score; this release generates it, aggregates it, and closes the loop back to `action-translation`'s glossary. The data goals proposed for this milestone (an OpenAI baseline, ≥100 judgments from ≥2 judges, the first upstream glossary PR) move to 0.7.0.

### Added

- **Central Elo recomputation** (PR #35): New `qebench.scoring.ratings` replays the committed `results/judgments/*.jsonl` into ratings, so the logs rather than the gitignored `elo.json` are the source of truth. `qebench export` writes a seventh file, `ratings.json`, and the dashboard gained a **Model Ratings** section. A contributor's judgments now count as soon as they are pushed. Ratings are reported at two granularities — `by_model` and `by_model_prompt` — because `model:prompt` labelling only arrived in v0.4.0 and a bare label cannot be attributed to a prompt after the fact. Neither is a superset of the other, so both carry match counts.
- **`qebench validate --strict`** (PR #34): Promotes en/zh alignment warnings to errors. CI runs it, so a misaligned entry can no longer land on `main` with a green build.
- **`qebench translate --uniform`** (PR #32): Opts out of the new consensus-weighted draw.
- **Formatting scores on every run record** (PR #32): `qebench run` stamps a `formatting` dict (`directive_balance`, `fence_consistency`, `code_block_integrity`, `fullwidth_punctuation`, `directive_spacing`) onto each output. `formatting_score()` shipped in v0.5.0 but nothing outside the judge panel had called it.
- **`qebench.scoring.alignment`** (PR #34): One en/zh alignment rule, shared by the seeder, `scripts/audit_alignment.py` and `qebench validate`, so seeded data passes the audit by construction.
- **`scripts/glossary_syncback.py`** (PR #32): Closes the benchmark → `action-translation` loop (REVIEW.md Should-Do #8). Compares human-verified translations and model consensus against the upstream glossary and emits corrections, additions, and terms needing stronger context. Emits candidates only — never edits the glossary, pushes, or opens a PR. `--min-annotators` (default 2), `--output-dir`. First run: 2 corrections, 45 needs-context.
- **`scripts/analyze_runs.py`** (PR #32): Aggregates cost, formatting pass rates, agreement and verbosity into the `results/model-outputs/NOTES.md` tables. Retroactively scores records written before the `formatting` field existed, so the April runs stay comparable.
- **`scripts/audit_alignment.py`** (PR #32): Read-only en/zh alignment audit over the seeded dataset.
- **Benchmark data**: 24 runs covering 2 Claude models × 4 prompts × 3 entry types — 3,288 translations. Sentences and paragraphs had never been benchmarked. `qebench judge` goes from 314 term-only matchups to 411 across all entry types, 380 of them discriminating.

### Fixed

- **Misaligned seeded references** (PR #34, issue #31): 11 entries whose `zh` was not a translation of its `en` — five a different passage, two truncated, one with a case-broken reference target, three lossy where upstream had improved. Each replacement was pulled from the paired lecture repos, and every entry kept its id so existing attempts and judgments stay attached. The audit reports 0 of 97 flagged, down from 12. Root cause was `_shared_markers` accepting any pair that shared a single math span, then skipping the length check entirely.
- **Corrupt result files no longer take down commands** (PRs #28, #29, #33): `qebench judge` had no guard at all, so one malformed line killed a whole session; `export` runs in the docs-deploy workflow, so a bad file failed the dashboard build for everyone. `UnicodeDecodeError` subclasses `ValueError`, so the `except (JSONDecodeError, OSError)` idiom never caught it, and it is raised lazily by the file iterator rather than by `json.loads`. Files are now read as `utf-8-sig`, so a Windows BOM no longer discards a recoverable file.
- **XP could be silently reset** (PR #33): `award_xp` reads, adds and writes back, so treating an unreadable file as "start from zero" would have overwritten a contributor's only XP record. It now warns and skips the award, leaving the file untouched.
- **False negatives in `check_fullwidth_punctuation`** (PR #32): Ordered-list markers, decimals, thousands separators and URLs were counted as ASCII punctuation errors — a correctly translated numbered paragraph scored 0.58 on its `1.` markers alone. The URL pattern is also CJK-bounded now; matching `\S+` swallowed the rest of the line in Chinese prose, which has no inter-word spaces, hiding every error after a link.

### Changed

- `qebench translate` weights its draw toward entries exactly one annotator short of consensus, and never re-serves an entry to someone who already translated it — a repeat from the same person adds no annotator coverage. Only 16 entries had two or more attempts. Pass `--uniform` for the previous behaviour.
- `load_elo_ratings()` rebuilds from the committed judgment logs when the cache is missing or corrupt, instead of restarting everyone at `DEFAULT_RATING`. A cache with a bad payload is moved aside to `elo.json.corrupt` first; one that merely failed to open is left alone. A rebuilt cache is not byte-identical to an incrementally grown one, since `update_model_elos` rounds after every judgment and the rebuild rounds once at the end.
- `scripts/seed_from_lectures.py` refuses to seed any pair the shared alignment rule rejects.
- `results/xp/*.json` is written with `ensure_ascii=False`, so CJK is stored literally rather than as `\uXXXX` escapes.
- `qebench export` writes 7 JSON files, up from 6.
- Contributors must cut branches from a freshly pulled `main` (PR #33): RAs push translation records straight to `main`, so a local `main` goes stale on its own and a stale base still merges cleanly.
- Tests: 262 → 626.

### Notes for anyone comparing against earlier data

- **Full-width punctuation scores are not comparable across this release.** The `check_fullwidth_punctuation` fix above changes the metric itself, so figures recorded before 2026-08-19 cannot be compared with those after it. `scripts/analyze_runs.py` recomputes retroactively, so regenerating a report is the reliable way to compare.
- **`cli_version` names the last *released* version, not the code that wrote the record.** It is read from installed package metadata, so a record written from a working tree carries the version of the last release installed there. This repo's own log contains `type: "consensus"` records stamped `0.3.1`, though consensus shipped in v0.4.0. `qebench.scoring.ratings` therefore determines a record's score scale from its own scores and uses the stamp only to break a tie. The v0.1.0 note below describing `cli_version` as sufficient "for future schema migration" is optimistic for the same reason.
- **Two paragraph entries had their English replaced**, not just their reference: `para-001` (notation changed upstream) and `para-014` (exercise relettered). 16 of the 3,288 committed model outputs are translations of the superseded English. Each record stores its own `source_text`, so every run stays internally consistent.

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

[0.6.0]: https://github.com/QuantEcon/benchmark.translate-zh-cn/releases/tag/v0.6.0
[0.5.0]: https://github.com/QuantEcon/benchmark.translate-zh-cn/releases/tag/v0.5.0
[0.4.0]: https://github.com/QuantEcon/benchmark.translate-zh-cn/releases/tag/v0.4.0
[0.3.1]: https://github.com/QuantEcon/benchmark.translate-zh-cn/releases/tag/v0.3.1
[0.3.0]: https://github.com/QuantEcon/benchmark.translate-zh-cn/releases/tag/v0.3.0
[0.2.1]: https://github.com/QuantEcon/benchmark.translate-zh-cn/releases/tag/v0.2.1
[0.2.0]: https://github.com/QuantEcon/benchmark.translate-zh-cn/releases/tag/v0.2.0
[0.1.1]: https://github.com/QuantEcon/benchmark.translate-zh-cn/releases/tag/v0.1.1
[0.1.0]: https://github.com/QuantEcon/benchmark.translate-zh-cn/releases/tag/v0.1.0
