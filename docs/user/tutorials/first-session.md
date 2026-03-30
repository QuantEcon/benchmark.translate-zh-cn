# Tutorial: Your First Translation Session

This tutorial walks you through a complete translation session — from setup
to submitting your results and seeing them on the dashboard.

## Prerequisites

Make sure you've completed [Getting Started](../getting-started.md):
- `gh auth login` done
- Repo cloned and `uv sync` run
- `uv run qebench doctor` passes all checks

## Step 1: Check Your Dataset

```bash
uv run qebench stats
```

You should see the coverage panel and domain table. The dataset is pre-seeded
with 300+ economics terms — enough to start practicing immediately.

## Step 2: Start a Short Session

Let's try a 3-entry session with basic-level terms:

```bash
uv run qebench translate -n 3 --difficulty basic
```

Your GitHub username is detected automatically from `gh auth`.

## Step 3: Translate Each Entry

For each entry, you'll see a panel like:

```
╭──────── TERM ────────╮
│                       │
│  inflation            │
│                       │
│  term-001 · economics │
│           · basic     │
╰───────────────────────╯
? Your translation (中文):
```

Type your Chinese translation and press Enter.

## Step 4: Review Your Score

After each answer, you'll see a comparison:

```
╭────────── Result ──────────╮
│  Your answer:  通货膨胀     │
│  Reference:    通货膨胀     │
│  Score:        ★ Exact!    │
╰────────────────────────────╯
```

The scoring uses character-level overlap:
- **★ Exact match** — you nailed it
- **◉ Close (≥70%)** — most characters match
- **○ Partial (≥40%)** — some overlap, review the reference
- **△ Keep practicing** — quite different from reference

## Step 5: Session Summary

After completing all entries, you'll see:

```
╭─── Session Summary ───╮
│  Completed:  3/3       │
│  Avg overlap: 85%      │
│  XP earned:  +30       │
│  Total XP:   30        │
╰────────────────────────╯
```

Each completed translation earns 10 XP. Your results are saved locally to
`results/translations/{your-username}.jsonl` and your XP to
`results/xp/{your-username}.json`.

## Step 6: Submit Your Results

Push your work to GitHub so it appears on the dashboard:

```bash
uv run qebench submit
```

This pulls the latest changes, commits your results, and pushes — all in one command.

```
╭────── Submitted as alice ──────╮
│  ✓ 1 result file(s)           │
╰────────────────────────────────╯
```

Once pushed, the CI workflow rebuilds the dashboard with your activity and XP.

## Step 7: Try Different Filters

Focus on a specific domain:

```bash
uv run qebench translate -d mathematics
```

Or crank up the difficulty:

```bash
uv run qebench translate --difficulty advanced -n 10
```

## Next Steps

- **Add entries**: See [Contributing Entries](contributing-entries.md) to grow the dataset
- **Check progress**: `qebench stats` shows overall dataset coverage
- **View dashboard**: check the [live dashboard](../../dashboard/) for leaderboard and activity
- See the full [CLI Reference](../cli-reference.md) for all options
