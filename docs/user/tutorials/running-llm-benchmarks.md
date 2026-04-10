# Tutorial: Running LLM Benchmarks

This tutorial shows how to use `qebench run` to batch-translate dataset
entries using LLM providers, and then evaluate the results with `qebench judge`.

## Prerequisites

- You've completed [Getting Started](../getting-started.md)
- Install the LLM dependencies:

```bash
uv sync --extra llm
```

- Set your API key as an environment variable:

```bash
# For Claude (Anthropic)
export ANTHROPIC_API_KEY=sk-ant-...

# For OpenAI
export OPENAI_API_KEY=sk-...
```

## Step 1: Preview with Dry Run

Before making API calls, preview what will be translated:

```bash
uv run qebench run --dry-run
```

This shows the first 5 entries that would be translated, without calling the
API:

```
╭──── qebench run ────╮
│ Provider: claude     │
│ Model:    (default)  │
│ Prompt:   default    │
│ Entries:  314 terms  │
╰──────────────────────╯

Dry run — no API calls will be made.
  term-001: inflation...
  term-002: gross domestic product...
  term-003: supply and demand...
  term-004: equilibrium...
  term-005: monetary policy...
  ... and 309 more
```

## Step 2: Run a Small Batch

Start with a small batch to verify everything works:

```bash
uv run qebench run -n 10
```

This translates 10 terms using the default provider (Claude) and prompt.
You'll see a progress spinner, then a summary:

```
╭──────── Run Summary ─────────╮
│ Entries translated         10 │
│ Total tokens            2,340 │
│ Total cost            $0.0035 │
│ Avg latency              245ms│
│ Output file  results/model-…  │
╰──────────────────────────────╯
```

Results are saved as JSONL to `results/model-outputs/`.

## Step 3: Try Different Providers

Compare Claude and OpenAI on the same entries:

```bash
# Claude (default)
uv run qebench run -n 20 -d economics

# OpenAI
uv run qebench run -n 20 -d economics --provider openai
```

Each run creates a separate output file, so results are never overwritten.

## Step 4: Use Different Models

Override the default model for a provider:

```bash
uv run qebench run --provider openai --model gpt-5.4-mini -n 10
```

## Step 5: Try Different Prompt Templates

Prompt templates live in the `prompts/` directory. The project ships with four:

- `default` — general-purpose translation prompt
- `academic` — emphasizes formal academic register
- `action-basic` — MyST Markdown-aware rules (preserves directives, code, math fencing)
- `action-new` — MyST rules + glossary injection from `action-translation`

```bash
# Academic prompt
uv run qebench run --prompt academic -n 20

# Action-translation style (MyST-aware, no glossary)
uv run qebench run --prompt action-basic -n 20

# Action-translation style with glossary injection
uv run qebench run --prompt action-new -n 20

# Compare against default on the same domain
uv run qebench run --prompt default -n 20 -d economics
```

The `action-new` template automatically loads the glossary from
`action-translation`'s GitHub repository (configured in `config.yaml`).
See [Glossary & Prompt Templates](glossary-and-prompts.md) for full details.

## Step 6: Translate Different Entry Types

By default, `qebench run` translates terms. Use `--type` for other types:

```bash
# Translate sentences
uv run qebench run --type sentences -n 10

# Translate paragraphs
uv run qebench run --type paragraphs -n 5
```

Paragraphs are the most challenging and informative entry type for benchmarking.
They include MyST feature flags (`contains_directives`, `contains_roles`,
`contains_mixed_fencing`) that help the automated formatting validators
determine which checks apply.

## Step 7: Judge the Results

Once you have model outputs, use `qebench judge` to compare them:

```bash
uv run qebench judge -n 10
```

The judge reveal panel now shows **formatting scores** alongside the existing
reference overlap and glossary compliance metrics. This lets you see whether
a model broke directives, mixed fence markers, or used ASCII punctuation
instead of fullwidth characters.

See [Judging Translations](judging-translations.md) for the full walkthrough.

## Step 8: Submit Results

Push model outputs and judgments to GitHub:

```bash
uv run qebench submit
```

## Output Format

Each run produces a JSONL file in `results/model-outputs/` with one record
per entry:

```json
{
  "entry_id": "term-001",
  "source_text": "inflation",
  "translated_text": "通货膨胀",
  "model": "claude-sonnet-4-6",
  "provider": "claude",
  "prompt_template": "default",
  "input_tokens": 123,
  "output_tokens": 45,
  "cost_usd": 0.001044,
  "latency_ms": 345.6
}
```

## Quick Reference

```bash
# Basic run (all terms, Claude, default prompt)
uv run qebench run

# Targeted run
uv run qebench run -n 20 -d economics --type sentences

# Compare providers
uv run qebench run -n 50 --provider claude
uv run qebench run -n 50 --provider openai

# Compare prompts (all 4)
uv run qebench run -n 50 --prompt default
uv run qebench run -n 50 --prompt academic
uv run qebench run -n 50 --prompt action-basic
uv run qebench run -n 50 --prompt action-new

# Dry run to preview
uv run qebench run --dry-run --type paragraphs
```

## Next Steps

- **Judge results**: See [Judging Translations](judging-translations.md) to evaluate model outputs
- **Check leaderboard**: `qebench stats` shows Elo ratings and XP rankings
- **Add custom prompts**: Create a new `.txt` file in `prompts/` and pass its name with `--prompt`
- **Glossary & prompts**: See [Glossary & Prompt Templates](glossary-and-prompts.md) for details on glossary injection
- **Seed more data**: See [Seeding from Lectures](../../developer/seeding-from-lectures.md) to extract sentence/paragraph pairs (developer guide)
