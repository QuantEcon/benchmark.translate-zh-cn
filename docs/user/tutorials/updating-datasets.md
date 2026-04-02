# Tutorial: Updating Datasets

This tutorial explains how to keep the benchmark datasets up to date
and how the context enrichment pipeline works. Run these steps before
starting any translation session.

## Prerequisites

- Repo cloned and `uv sync` run
- `gh auth login` done
- Internet connection (for git pulls and lecture repo cloning)

## Step 1: Run `qebench update`

```bash
uv run qebench update
```

This single command performs three things in order:

1. **Pull latest code** — runs `git pull --rebase` so you have everyone's
   latest contributions and any CLI updates.

2. **Sync dependencies** — runs `uv sync` to install or update any changed
   Python packages.

3. **Enrich term contexts** — clones (or updates) four QuantEcon lecture
   repositories into `.cache/lectures/` and scans them for real-world usage
   sentences containing each term. Up to 5 context sentences are stored per
   term.

The lecture repos scanned are:

| Repository | Content |
|---|---|
| `lecture-python-programming` | Python programming lectures |
| `lecture-python-intro` | Introductory economics with Python |
| `lecture-python.myst` | Intermediate quantitative economics |
| `lecture-python-advanced.myst` | Advanced quantitative economics |

The first run clones all four repos (shallow clone, ~30 seconds each).
Subsequent runs do `git pull` and finish quickly.

## Step 2: Verify with `qebench stats`

After updating, check that enrichment worked:

```bash
uv run qebench stats
```

The stats output shows overall dataset coverage. You can also inspect
individual data files in `data/terms/` to see the `contexts` field:

```json
{
  "id": "term-042",
  "en": "dynamic programming",
  "zh": "动态规划",
  "domain": "dynamic-programming",
  "difficulty": "intermediate",
  "contexts": [
    {
      "text": "Dynamic programming is a powerful technique for solving sequential decision problems.",
      "source": "lecture-python-intro/dp/intro.md"
    }
  ]
}
```

## Step 3: See Contexts During Translation

When you run `qebench translate`, terms that have context sentences display
a random usage example to help you choose the right translation:

```
╭──────── TERM ────────╮
│                       │
│  dynamic programming  │
│                       │
│  term-042             │
│  · dynamic-programming│
│  · intermediate       │
│                       │
│  📖 "Dynamic          │
│  programming is a     │
│  powerful technique    │
│  for solving           │
│  sequential decision   │
│  problems."            │
│  — lecture-python-intro│
╰───────────────────────╯
```

This shows the English term used in context, helping you select the most
appropriate Chinese translation for the domain.

## How the Pipeline Works

```
qebench update
  ├── git pull --rebase
  ├── uv sync
  └── enrich contexts
        ├── clone/pull lecture repos → .cache/lectures/
        ├── scan .md files for term occurrences
        ├── extract surrounding prose sentences
        ├── store up to 5 per term (deterministic, sorted)
        └── write back only changed data files
```

**Key details:**

- The `.cache/` directory is gitignored — lecture repos are local only.
- Only data files with newly enriched terms are rewritten (unchanged files
  are skipped).
- Context selection is deterministic (sorted alphabetically, first 5 chosen)
  so results are reproducible across machines.
- The wrapper format `{"version": ..., "entries": [...]}` is preserved when
  present in data files.

## Committing Updated Data

After `qebench update` enriches terms, the `data/terms/*.json` files may
have new `contexts` fields. These changes should be committed and pushed so
the whole team benefits:

```bash
git add data/
git commit -m "chore: update term contexts from lecture repos"
git push
```

Or include them as part of your normal contribution workflow — enriched
contexts are committed alongside translation results.

## Troubleshooting

**Clone fails behind a firewall**: The lecture repos are public on GitHub.
If cloning fails, check your network connection and try again.

**No contexts found for a term**: Not every term appears in the lecture
corpus. Specialized or rare terms may have zero context sentences — this is
normal and doesn't affect translation.

**Stale contexts after lecture updates**: Run `qebench update` again — it
pulls the latest lecture content and re-scans all terms.
