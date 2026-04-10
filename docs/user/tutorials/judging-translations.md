# Tutorial: Judging Translations

This tutorial walks you through a judge session — comparing anonymous
translations side-by-side, scoring them, and building Elo ratings that show
which translation approaches work best.

## Prerequisites

- You've completed [Getting Started](../getting-started.md)
- Model outputs exist in `results/model-outputs/`. If they don't, run
  `qebench run` first (see [Running LLM Benchmarks](running-llm-benchmarks.md))

## Why Judge?

Human judgments are the gold standard for translation quality. `qebench judge`
pairs two translations of the same source text — from LLM models or the human
reference — and asks you to rate each on accuracy and fluency, then pick a
winner. Your judgments update Elo ratings that rank the models over time.

## Step 1: Update and Check Stats

Always start with the latest data:

```bash
uv run qebench update
uv run qebench stats
```

## Step 2: Start a Judge Session

Run a quick 5-round session:

```bash
uv run qebench judge -n 5
```

You'll see a session header:

```
╭──────── Judge Session ────────╮
│  Rounds: 5   Domain: all      │
│  Models: 2   User: alice       │
╰───────────────────────────────╯
```

## Step 3: Read the Source Text

Each round shows the English source in a panel:

```
╭──── Judge  (Round 1)  TERM ────╮
│                                 │
│  inflation                      │
│                                 │
│  term-001 · economics · basic   │
╰─────────────────────────────────╯
```

Read the source carefully before looking at the translations.

## Step 4: Compare Translations A and B

Two translations appear side by side:

```
╭── Translation A ──╮   ╭── Translation B ──╮
│  通货膨胀          │   │  通胀              │
╰───────────────────╯   ╰───────────────────╯
```

The labels A and B are randomized — you don't know which model produced
which translation until the reveal.

## Step 5: Pick the Winner

After comparing both translations, pick the overall winner:

```
Which is better overall?
  A is better
❯ B is better
  Tie — equally good
  Neither — both are poor
```

If both are equally good, pick **Tie**. If both are poor and neither is
acceptable, pick **Neither**. Don't overthink it — go with your first
instinct after reading both.

## Step 6: Score Each Translation

If you picked A or B as the winner, you'll be asked to rate each translation
on two dimensions. (For **Tie** and **Neither**, scoring is skipped.)

```
Rate Translation A:
  Accuracy (1-10): ▸ 9
  Fluency (1-10):  ▸ 8
```

Then rate **Translation B** the same way:

```
Rate Translation B:
  Accuracy (1-10): ▸ 7
  Fluency (1-10):  ▸ 9
```

**Accuracy** means how faithfully the translation captures the meaning.
**Fluency** means how natural and readable the Chinese is.

## Step 7: See the Reveal

After picking, the result panel shows who won, automated scores, and
formatting checks:

```
╭──────────── Result ────────────╮
│          A (claude)  B (human) │
│ Winner                B wins!  │
│ Elo         1520       1480    │
│ Ref. overlap  85%      100%   │
│ Glossary      90%      100%   │
│ Punctuation   92%       98%   │
│ Directives    ✓         ✓     │
╰────────────────────────────────╯
```

- **Elo** — model skill rating (higher = better track record)
- **Ref. overlap** — character similarity to the reference translation
- **Glossary** — percentage of key terms correctly translated
- **Punctuation** — fullwidth punctuation compliance (，。！ vs ,.!)
- **Directives** — whether MyST directive open/close pairs are balanced

The formatting scores are computed automatically — you don't need to check
MyST syntax yourself. Over time, you'll learn to associate certain models
with formatting problems, which helps `action-translation` improve its prompts.

## Step 8: Complete the Session

After all rounds, you'll see:

```
╭─── Session Summary ───╮
│  Rounds completed: 5/5 │
│  XP earned:  +25        │
│  Total XP:   75         │
╰─────────────────────────╯
```

Each judgment earns **5 XP**.

## Step 9: Submit Your Judgments

Push your results to GitHub:

```bash
uv run qebench submit
```

Your judgments are saved in `results/judgments/{your-username}.jsonl` and Elo
ratings are updated in `results/elo.json`.

## Filtering by Domain

Focus your judgments on a specific domain:

```bash
uv run qebench judge -n 10 -d economics
```

This is useful when you have domain expertise — your ratings will be more
precise for terms you know well.

## Matchup Strategy

The judge system pairs translations intelligently:

- **2+ models** translated the same entry → two models are paired
- **1 model** translated an entry → model is paired against the human reference
- **0 models** → entry is skipped (nothing to compare)
- **Identical pairs** → automatically skipped (nothing to judge)

You can exit a session early at any prompt by pressing Ctrl+C — completed
rounds are saved.

## Next Steps

- **Translate more entries**: See [Your First Translation Session](first-session.md) to collect more data
- **Run more models**: See [Running LLM Benchmarks](running-llm-benchmarks.md) to generate model outputs
- **Compare prompts**: See [Glossary & Prompt Templates](glossary-and-prompts.md) to test action-translation prompts
- **Seed more data**: See [Seeding from Lectures](seeding-from-lectures.md) to extract sentence/paragraph pairs
- **Check the leaderboard**: `qebench stats` shows the XP leaderboard and dataset coverage
