# Getting Started

## Prerequisites

- **Python 3.11+**
- [**uv**](https://docs.astral.sh/uv/) — fast Python package manager

Install uv if you don't have it:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## Installation

```bash
git clone https://github.com/QuantEcon/benchmark.translate-zh-cn.git
cd benchmark.translate-zh-cn
uv sync
```

This installs `qebench` and all dependencies into a local virtual environment.

## Verify It Works

```bash
uv run qebench stats
```

You should see a coverage panel showing the current dataset status:

```
╭─────────────────── Dataset Coverage ────────────────────╮
│   Terms:       ██████████████████░░░░░░░░░░░░  314/500  │
│   Sentences:   ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░   0/100  │
│   Paragraphs:  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░   0/30   │
╰─────────────────────────────────────────────────────────╯
```

## Next Steps

- [Your First Translation Session](tutorials/first-session.md) — the main interactive mode
- [CLI Reference](cli-reference.md) — all available commands
