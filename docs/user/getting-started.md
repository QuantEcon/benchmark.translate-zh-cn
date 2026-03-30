# Getting Started

## Prerequisites

- **Python 3.11+**
- [**uv**](https://docs.astral.sh/uv/) — fast Python package manager
- [**GitHub CLI (gh)**](https://cli.github.com/) — for authentication and submitting work

Install uv if you don't have it:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## Setup

```bash
# 1. Authenticate with GitHub (one-time)
gh auth login

# 2. Clone and install
git clone https://github.com/QuantEcon/benchmark.translate-zh-cn.git
cd benchmark.translate-zh-cn
uv sync

# 3. Verify your setup
uv run qebench doctor
```

The doctor command checks that everything is configured correctly:

```
  ✓ GitHub CLI (gh) installed
  ✓ GitHub authenticated as your-username
  ✓ Git installed
  ✓ Inside a git repository
  ✓ Remote origin configured
  ✓ config.yaml found
  ✓ Dataset has entries
  ✓ uv package manager installed
```

## Quick Start

```bash
# Check dataset status
uv run qebench stats

# Practice translating
uv run qebench translate

# Contribute new entries
uv run qebench add

# Submit your work to GitHub (updates the dashboard)
uv run qebench submit
```

Your GitHub username is detected automatically — no need to pass `--user`.

## How It Works

1. **You run commands** — `translate` or `add` save results to per-user files locally
2. **You submit** — `qebench submit` commits and pushes your work to GitHub
3. **Dashboard updates** — a GitHub Actions workflow exports data and rebuilds the dashboard

All data files are per-user (`data/terms/your-username.json`, `results/xp/your-username.json`), so there are no merge conflicts between contributors.

## Next Steps

- [Your First Translation Session](tutorials/first-session.md) — the main interactive mode
- [CLI Reference](cli-reference.md) — all available commands
