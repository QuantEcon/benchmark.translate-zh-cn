# Changelog

All notable changes to `qebench` will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

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

[0.1.0]: https://github.com/QuantEcon/benchmark.translate-zh-cn/releases/tag/v0.1.0
