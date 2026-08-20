# benchmark.translate-zh-cn

Benchmark dataset and CLI tool for evaluating English-Chinese translation quality in academic economics and mathematics.

## Overview

Three things that work together:

1. **A gold-standard test dataset** of English-Chinese translation pairs (terms, sentences, paragraphs)
2. **A CLI tool (`qebench`)** for contributing translations, judging model outputs, and running benchmarks
3. **A results website** (GitHub Pages) showing leaderboards, model Elo ratings, and coverage progress

## Quick Start

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone and install
git clone https://github.com/QuantEcon/benchmark.translate-zh-cn.git
cd benchmark.translate-zh-cn
uv sync

# Check dataset stats
uv run qebench stats

# Start translating (the fun part)
uv run qebench translate

# Same, but sample uniformly instead of prioritising entries
# that are one attempt away from having a second annotator
uv run qebench translate --uniform
```

## Commands

```
qebench stats        Show dataset coverage, domain breakdown, XP leaderboard
qebench translate    Translate & Compare mode (can you beat the AI?)
qebench judge        Judge mode (rate anonymous translations, build Elo)
qebench add          Add new test entries to the dataset
qebench run          Run benchmark against LLM models
qebench validate     Check every dataset file against the Pydantic schemas
qebench submit       Pull, commit, and push your data and results to GitHub
qebench export       Export dataset and results to JSON for the website
qebench doctor       Run preflight checks (gh, git, auth, remote, config, data, uv)
qebench update       Pull latest code, data, and dependencies from GitHub
```

Elo is not part of `stats`. `qebench export` recomputes model ratings from the
committed judgment logs into `ratings.json`, and the dashboard renders them
under **Model Ratings**.

## Dataset

Translation pairs at three granularities sourced from QuantEcon lectures:

| Level | Target | Current | Description |
|---|---|---|---|
| Terms | 500+ | 314 | Single terms with standard translations |
| Sentences | 100+ | 80 | One-sentence definitions or statements |
| Paragraphs | 30+ | 30 | Multi-sentence explanations (may include math/code/directives) |

Sentences and paragraphs are seeded from aligned English/Chinese lecture pairs
using `scripts/seed_from_lectures.py`. See [Seed Script Guide](docs/developer/seeding-from-lectures.md).

## Prompt Templates

Four prompt templates in `prompts/` for LLM benchmarking:

| Template | Description |
|---|---|
| `default` | General-purpose translation prompt |
| `academic` | Formal academic register emphasis |
| `action-basic` | MyST Markdown-aware rules (directive/math/code preservation) |
| `action-new` | MyST rules + glossary injection from `action-translation` |

Use `action-basic` and `action-new` to benchmark prompts that mirror
[action-translation](https://github.com/QuantEcon/action-translation)'s
production translation rules. See [Glossary & Prompt Templates Tutorial](docs/user/tutorials/glossary-and-prompts.md).

## Automated Formatting Checks

`qebench judge` includes automated MyST formatting fidelity scoring. These
checks run on each translation pair and are displayed in the reveal panel:

- **Directive balance** — open/close pairs match between source and translation
- **Fence consistency** — no mixed `$$` / `` ```{math} `` markers
- **Code block preservation** — code blocks unchanged
- **Full-width punctuation** — zh-cn uses `，。！？` not `,.!?`
- **Directive spacing** — space between CJK characters and MyST directives

See [Architecture: Scoring Module](docs/developer/architecture.md#scoring-module) for implementation details.

## Feedback Loop

The benchmark is not a leaderboard for its own sake. It exists to improve
[action-translation](https://github.com/QuantEcon/action-translation), the
GitHub Action that actually translates the QuantEcon lectures.

The cycle: the benchmark runs the same models against prompt templates that
mirror action-translation's production prompts → it evaluates the output with
human judgment plus automated scoring → findings flow back as glossary
corrections, glossary additions, prompt refinements, and model-selection
guidance → action-translation translates better.

The benchmark does not ingest action-translation's output directly. `qebench
run` calls the providers itself using the `action-basic` and `action-new`
templates, which reproduce action-translation's rules; that is what makes the
findings transferable.

Each contribution mode feeds a different part of the cycle:

| Command | What it contributes |
|---|---|
| `qebench translate` | Human translations, and the *why* when a translator diverges from the stored reference |
| `qebench add` | New test entries — grows coverage of terms, sentences, and paragraphs |
| `qebench judge` | Head-to-head ratings that produce the Elo rankings and model-selection guidance |
| `qebench run` | The model outputs being judged, per model and per prompt template |

**Closing the loop.** `scripts/glossary_syncback.py` compares human-verified
translations and model consensus against the upstream `action-translation`
glossary and emits three kinds of candidate: **corrections** (human translators
agree on a translation that differs from the glossary), **additions** (terms the
glossary does not cover yet), and **needs-context** terms (models get them wrong
without glossary guidance, so the entry needs stronger context).

```bash
# Compare benchmark data against the upstream glossary
uv run python scripts/glossary_syncback.py

# Require three agreeing annotators and write the reports elsewhere
uv run python scripts/glossary_syncback.py --min-annotators 3 --output-dir /tmp/syncback
```

`--min-annotators` defaults to `2`: that many distinct human translators must
agree on the same translation before a correction is proposed.

Reports land in `results/glossary-syncback/`. They are candidates, not commits:
a maintainer reviews them and takes the accepted ones upstream as a PR against
`action-translation`'s `glossary/zh-cn.json`.

**Worked example.** The April term runs caught Haiku translating "Arrow
securities" as 箭头证券 — a literal "arrow" — rather than 阿罗证券, which
transliterates Kenneth Arrow's name. That is exactly the class of error a
glossary entry prevents, and exactly what sync-back pushes upstream.

See [REVIEW.md §8](REVIEW.md#8-the-feedback-loop-benchmark--action-translation)
for the longer design discussion.

## Development

```bash
# Install with dev dependencies
uv sync --extra dev

# Run tests
uv run pytest

# Lint
uv run ruff check src/ tests/
```

## Related

- [action-translation](https://github.com/QuantEcon/action-translation) — the GitHub Action this benchmark evaluates
- [QuantEcon lectures](https://quantecon.org/) — source material for the dataset
- [REVIEW.md](REVIEW.md) — design review and gap analysis of both projects

## License

MIT
