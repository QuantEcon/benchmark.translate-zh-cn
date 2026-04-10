# Documentation

**[Dashboard](dashboard/)** — Live leaderboard, dataset coverage, and activity feed.

## User Guide (`user/`)

Documentation for RAs and contributors using `qebench`.

- [Getting Started](user/getting-started.md) — Install, configure, run your first command
- [Working with uv](user/uv-guide.md) — Python package manager intro and common workflows
- [CLI Reference](user/cli-reference.md) — All commands, options, and examples
- **Tutorials**
  - [Your First Translation Session](user/tutorials/first-session.md) — Walk through `qebench translate`
  - [Contributing Entries](user/tutorials/contributing-entries.md) — Grow the benchmark with `qebench add`
  - [Updating Datasets](user/tutorials/updating-datasets.md) — Keep data current with `qebench update`
  - [Judging Translations](user/tutorials/judging-translations.md) — Compare translations and build Elo ratings with `qebench judge`
  - [Running LLM Benchmarks](user/tutorials/running-llm-benchmarks.md) — Batch translate with Claude or OpenAI via `qebench run`
  - [Glossary & Prompt Templates](user/tutorials/glossary-and-prompts.md) — Use action-translation prompts with glossary injection

## Developer Guide (`developer/`)

Documentation for developers building and maintaining `qebench`.

- [Architecture](developer/architecture.md) — Module structure, data flow, design decisions
- [Data Models](developer/data-models.md) — Pydantic schemas, JSON format, validation
- [Contributing](developer/contributing.md) — Development workflow, testing, code style
- [Seeding from Lectures](developer/seeding-from-lectures.md) — Extract aligned sentence/paragraph pairs from lecture repos
