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
uv run qebench translate --random
```

## Commands

```
qebench stats        Show dataset coverage, Elo rankings, leaderboard
qebench translate    Translate & Compare mode (can you beat the AI?)
qebench judge        Judge mode (rate anonymous translations, build Elo)
qebench add          Add new test entries to the dataset
qebench run          Run benchmark against LLM models
qebench export       Export results for the website
```

## Dataset

Translation pairs at three granularities sourced from QuantEcon lectures:

| Level | Target | Current | Description |
|---|---|---|---|
| Terms | 500+ | 314 | Single terms with standard translations |
| Sentences | 100+ | 80 | One-sentence definitions or statements |
| Paragraphs | 30+ | 17 | Multi-sentence explanations (may include math/code/directives) |

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
