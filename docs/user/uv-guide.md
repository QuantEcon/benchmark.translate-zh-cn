# Working with uv

[uv](https://docs.astral.sh/uv/) is a fast Python package and project manager
written in Rust. It replaces `pip`, `venv`, `pip-tools`, and `pyenv` with a
single tool. This project uses uv for all dependency management.

## Installing uv

::::{tab-set}

:::{tab-item} macOS / Linux
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```
:::

:::{tab-item} Windows (PowerShell)
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```
:::

:::{tab-item} Homebrew
```bash
brew install uv
```
:::

::::

After installation, restart your terminal and verify:

```bash
uv --version
```

## Key Concepts

### `uv sync` — install everything

```bash
uv sync
```

This single command:

1. **Creates a virtual environment** (`.venv/`) if one doesn't exist
2. **Installs all dependencies** listed in `pyproject.toml`
3. **Installs the project itself** in editable mode (like `pip install -e .`)
4. **Locks versions** in `uv.lock` so everyone gets identical packages

You only need to run this once after cloning. Run it again if dependencies
change (i.e. someone updates `pyproject.toml`).

### `uv run` — run commands in the project environment

```bash
uv run qebench stats
uv run qebench translate -n 5
uv run pytest tests/ -v
```

`uv run` automatically activates the virtual environment for the command. You
never need to manually `source .venv/bin/activate`. This is the recommended way
to run all project commands.

:::{tip}
If you find typing `uv run` tedious, you *can* activate the virtual
environment directly:

```bash
source .venv/bin/activate   # macOS / Linux
qebench stats               # now works without `uv run`
```

But `uv run` is preferred — it always finds the right Python and environment,
even if you have multiple projects.
:::

### `uv add` — add a new dependency

```bash
uv add requests            # add a runtime dependency
uv add --dev ruff          # add a dev-only dependency
```

This updates `pyproject.toml` and `uv.lock` in one step. You don't edit
`pyproject.toml` by hand for dependencies.

## Common Workflows

### First-time setup

```bash
git clone https://github.com/QuantEcon/benchmark.translate-zh-cn.git
cd benchmark.translate-zh-cn
uv sync
uv run qebench doctor
```

### Daily use

```bash
uv run qebench translate       # practice translations
uv run qebench add             # add new entries
uv run qebench submit          # push your work
```

### Running tests (developers)

```bash
uv sync --extra dev             # install dev dependencies (pytest, ruff)
uv run pytest tests/ -v         # run all tests
uv run ruff check src/ tests/   # lint
uv run ruff format src/ tests/  # auto-format
```

### Updating after a `git pull`

If someone changed the dependencies:

```bash
git pull
uv sync
```

That's it — uv resolves and installs any new or changed packages.

## How uv Differs from pip

| Task | pip + venv | uv |
|---|---|---|
| Create environment | `python -m venv .venv` | `uv sync` (automatic) |
| Activate environment | `source .venv/bin/activate` | Not needed (`uv run`) |
| Install dependencies | `pip install -r requirements.txt` | `uv sync` |
| Install project | `pip install -e .` | `uv sync` (included) |
| Add a package | Edit requirements.txt + `pip install` | `uv add package` |
| Lock versions | `pip freeze > requirements.txt` | `uv.lock` (automatic) |
| Run a command | Must activate venv first | `uv run command` |

The key insight: **uv sync** does what 3-4 pip commands do, and **uv run**
removes the need to think about virtual environment activation.

## File Reference

| File | Purpose |
|---|---|
| `pyproject.toml` | Project metadata + dependency declarations |
| `uv.lock` | Exact locked versions (committed to git) |
| `.venv/` | Virtual environment directory (git-ignored) |
| `.python-version` | Python version for the project (if present) |

## Troubleshooting

**"uv: command not found"** — Restart your terminal after installing, or add
`~/.cargo/bin` (or `~/.local/bin`) to your `PATH`.

**"No Python found"** — uv can install Python for you:
```bash
uv python install 3.12
```

**"Packages out of date after git pull"** — Just run `uv sync` again.

**Want to start fresh?** — Delete `.venv/` and re-run `uv sync`:
```bash
rm -rf .venv
uv sync
```

## Further Reading

- [uv documentation](https://docs.astral.sh/uv/)
- [uv Getting Started guide](https://docs.astral.sh/uv/getting-started/)
- [Why uv?](https://docs.astral.sh/uv/#highlights) — speed benchmarks and feature overview
