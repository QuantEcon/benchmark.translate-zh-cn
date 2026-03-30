# CLI Reference

All commands available in `qebench`, organized by the typical daily workflow.

## `qebench update`

Pull the latest code, data, and dependencies from GitHub. **Run this at the
start of every session** to ensure you have everyone's latest contributions
and any CLI updates.

```bash
uv run qebench update
```

No options — it runs two steps:

1. **Pull** — `git pull --rebase` to get the latest code and data
2. **Sync** — `uv sync` to install any new or updated dependencies

If already up to date, it tells you so. If the pull fails (e.g. you have
uncommitted changes), resolve them first then try again.

:::{tip}
Both code and data live in the same repository, so a single `qebench update`
keeps everything in sync — no separate install step needed.
:::

---

## `qebench stats`

Show dataset coverage, domain breakdown, and progress toward targets.

```bash
uv run qebench stats
```

**Output includes:**
- Progress bars for terms, sentences, and paragraphs vs. targets
- Domain breakdown table with entry counts
- Total entries summary

No options — always shows the full dataset overview.

---

## `qebench translate`

Collect human translations. Presents English text, collects your Chinese
translation and a confidence rating, then reveals the reference for learning.
Every translation — including ones that differ from the reference — is
valuable data for understanding translation variation.

```bash
uv run qebench translate [OPTIONS]
```

| Option | Short | Default | Description |
|---|---|---|---|
| `--count` | `-n` | `5` | Number of entries per session |
| `--domain` | `-d` | all | Filter by domain (e.g. `economics`) |
| `--difficulty` | | all | Filter: `basic`, `intermediate`, or `advanced` |

Your GitHub username is detected automatically via `gh auth`.

**Examples:**

```bash
# Quick 3-term session on economics
uv run qebench translate -n 3 -d economics

# Practice advanced terms
uv run qebench translate --difficulty advanced

# Default session (5 random entries)
uv run qebench translate
```

**What's recorded per entry:**
- Your Chinese translation
- Confidence level (1–5)
- Character similarity to the reference (informational, not a grade)
- If your translation differs: the reason why (formal/informal register, regional preference, contextual, abbreviation, alternative technical term, or other)
- Optional notes for further explanation

Divergent translations are valuable — they help us understand cultural nuance and variation.

Each completed entry earns **10 XP**.

---

## `qebench add`

Contribute new terms, sentences, or paragraphs to the dataset through interactive prompts.

```bash
uv run qebench add
```

No options — the command walks you through the process:

1. **Choose entry type** — term, sentence, or paragraph
2. **Fill in fields** — English text, Chinese translation, domain, difficulty, etc.
3. **Preview** — see a summary before saving
4. **Confirm** — save to the appropriate domain JSON file
5. **Continue?** — option to add another entry

Each contributed entry earns **15 XP**.

---

## `qebench submit`

Pull latest changes, commit your data and results, and push to GitHub. This is the primary way to share your contributions.

```bash
uv run qebench submit
```

No options — it handles the full git workflow:

1. **Pull** — `git pull --rebase` to get latest changes
2. **Stage** — adds `data/` and `results/` directories
3. **Commit** — creates a commit attributed to your GitHub username
4. **Push** — pushes to `main`, which triggers a dashboard rebuild

If there are no local changes in `data/` or `results/`, it exits early.

---

## `qebench doctor`

Run preflight checks to verify your environment is set up correctly.

```bash
uv run qebench doctor
```

**Checks performed:**
- GitHub CLI (`gh`) installed
- GitHub authentication configured
- Git installed and inside a repo
- Remote origin configured
- `config.yaml` found
- Dataset has entries
- `uv` package manager available

Run this once after initial setup, or whenever something seems wrong.

---

## `qebench export`

Export dataset statistics and results to JSON files for the dashboard website.

```bash
uv run qebench export
```

Writes 6 JSON files to `docs/_static/dashboard/data/`:
- `coverage.json` — terms/sentences/paragraphs vs. targets
- `domains.json` — per-domain entry counts
- `difficulty.json` — basic/intermediate/advanced distribution
- `leaderboard.json` — XP rankings across users
- `activity.json` — recent translation attempts
- `samples.json` — sample terms for the browse section

This is run automatically by CI when changes are pushed.

---

## XP System

Actions earn experience points tracked per user:

| Action | XP per item |
|---|---|
| Translate an entry | 10 |
| Add a new entry | 15 |
| Judge a comparison | 5 |

XP is stored in `results/xp/{username}.json` and shown at the end of each session.
