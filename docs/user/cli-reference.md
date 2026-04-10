# CLI Reference

All commands available in `qebench`, organized by the typical daily workflow.

## `qebench update`

Pull the latest code, data, and dependencies from GitHub, then enrich term
contexts from QuantEcon lecture repos. **Run this at the start of every
session** to ensure you have everyone's latest contributions and any CLI
updates.

```bash
uv run qebench update
```

No options — it runs three steps:

1. **Pull** — `git pull --rebase` to get the latest code and data
2. **Sync** — `uv sync` to install any new or updated dependencies
3. **Enrich** — clone/update QuantEcon lecture repos into `.cache/lectures/`
   and add context sentences to terms that don't have them yet

The enrichment step scans four lecture repositories for sentences that use
each term, storing up to 5 example sentences per term. These context sentences
are shown during `qebench translate` to help you choose the right Chinese
translation. The lecture repos are cached locally (shallow clones, gitignored)
so subsequent runs only pull changes.

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
- XP leaderboard ranked by total XP (with translate/add/judge breakdown)
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

:::{note}
The translate command works with **terms** and **sentences** only. Paragraphs
are excluded because the CLI uses single-line text input, which is impractical
for multi-line content. To evaluate paragraph translations, use `qebench judge`
(which shows them read-only) or `qebench run` (which sends them to LLMs).
:::

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

For **terms** that have context sentences (populated by `qebench update`),
a random example sentence from a QuantEcon lecture is shown alongside the
term. This helps you understand how the term is used in practice and choose
the most appropriate Chinese translation.

Each completed entry earns **10 XP**. A `cli_version` field is automatically saved with every record for future schema migration.

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

Each contributed entry earns **15 XP**. A `cli_version` field is automatically saved with every entry.

---

## `qebench judge`

Judge anonymous translations head-to-head. Shows two translations of the same
source text, you rate each on accuracy and fluency, then pick a winner.
Results update Elo ratings for the models.

```bash
uv run qebench judge                       # Default: 10 rounds
uv run qebench judge -n 5                  # Quick 5-round session
uv run qebench judge -d economics          # Filter to economics entries
```

### Options

| Option | Short | Default | Description |
|---|---|---|---|
| `--count` | `-n` | `10` | Number of rounds per session |
| `--domain` | `-d` | all | Filter by domain |

### Prerequisites

Model outputs must exist in `results/model-outputs/`. Generate them with `qebench run` first.

### How It Works

1. Entries are paired with model translations from `results/model-outputs/`
2. Two translations are shown anonymously as **A** and **B**
3. You rate each on accuracy (0–5) and fluency (0–5)
4. You pick a winner (A, B, tie, or neither)
5. Elo ratings are updated; results saved to `results/judgments/`
6. The reveal panel shows model labels, Elo ratings, reference overlap,
   glossary compliance, and **formatting scores** (fullwidth punctuation %,
   directive balance)

Pick **Tie** if both translations are equally good. Pick **Neither** if both
translations are poor and neither is acceptable.

If two models have translated the same entry, they're paired directly.
If only one model has output, it's paired against the human reference.
Identical translation pairs are automatically skipped.

Each judgment earns **5 XP**.

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

## `qebench validate`

Validate all dataset JSON files against the Pydantic schemas. Useful for
checking your contributed entries before submitting.

```bash
uv run qebench validate
```

Checks every file in `data/terms/`, `data/sentences/`, and `data/paragraphs/`
against the corresponding model (Term, Sentence, Paragraph). Reports all
validation errors with file names and entry IDs, then exits non-zero if any
were found.

This also runs automatically in CI on every push and PR.

---

## `qebench run`

Batch translate dataset entries using an LLM provider. Results are saved to
`results/model-outputs/` as JSONL files.

```bash
uv run qebench run                             # Default: claude, all terms
uv run qebench run --provider openai            # Use OpenAI
uv run qebench run --model gpt-5.4-mini         # Override model
uv run qebench run --prompt academic            # Use academic prompt template
uv run qebench run --prompt action-new          # MyST-aware prompt with glossary
uv run qebench run --type sentences --domain economics  # Filter entries
uv run qebench run --count 10 --dry-run         # Preview without API calls
```

### Options

| Option | Default | Description |
|---|---|---|
| `--provider`, `-p` | `claude` | LLM provider: `claude`, `openai` |
| `--model`, `-m` | *(provider default)* | Override the default model (Claude: `claude-sonnet-4-6`, OpenAI: `gpt-5.4`) |
| `--prompt` | `default` | Prompt template name from `prompts/` |
| `--count`, `-n` | `0` (all) | Max entries to translate |
| `--domain`, `-d` | *(all)* | Filter entries by domain |
| `--type`, `-t` | `terms` | Entry type: `terms`, `sentences`, `paragraphs` |
| `--dry-run` | `false` | Preview entries without calling the API |

### Prompt Templates

Four prompt templates are available:

| Template | Description |
|---|---|
| `default` | General-purpose translation prompt |
| `academic` | Formal academic register emphasis |
| `action-basic` | MyST Markdown-aware rules (preserves directives, code, math fencing) |
| `action-new` | MyST rules + glossary injection from `action-translation` |

The `action-new` template uses the `{glossary}` placeholder, which is
automatically populated from `action-translation`'s glossary (fetched from
GitHub and cached locally in `.cache/glossary.json`). See
[Glossary & Prompt Templates Tutorial](tutorials/glossary-and-prompts.md).

### Prerequisites

Install LLM dependencies:

```bash
uv sync --extra llm
```

Set your API key via environment variable (`ANTHROPIC_API_KEY` or `OPENAI_API_KEY`).

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
