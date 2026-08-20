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
  term-001: Angle sum identities...
  term-002: Partial derivative...
  term-003: Taylor series...
  term-004: Trigonometric integrals...
  term-005: Asymptotic stability...
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

That glossary is around 5,200 tokens, and it is re-sent with every entry — for
314 short terms it is essentially the entire bill. `qebench run` prompt-caches
it by default, so it is paid for once per domain rather than once per entry.
Pass `--no-cache` to bill it every time, which is what the runs already in
`NOTES.md` did:

```bash
uv run qebench run --prompt action-new -n 20            # cached (default)
uv run qebench run --prompt action-new -n 20 --no-cache # every call pays in full
```

The run summary reports how many tokens were written to and read from the
cache, so it is easy to tell whether the cache is being hit. See
[prompt caching](../cli-reference.md#prompt-caching) for why a run writes one
cache entry per domain, and why a domain with a single entry is left uncached.

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
`contains_mixed_fencing`) that describe the structural complexity of each
paragraph for filtering and analysis.

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
per entry. This is a real record, from the Sonnet 4.6 / `default` run over
sentences:

```json
{
  "entry_id": "sent-073",
  "source_text": "This example was created by {cite}`bertsimas_tsitsiklis1997`",
  "translated_text": "此示例由 {cite}`bertsimas_tsitsiklis1997` 创建",
  "model": "claude-sonnet-4-6",
  "provider": "claude",
  "prompt_template": "default",
  "entry_type": "sentences",
  "domain": "optimization",
  "difficulty": "intermediate",
  "input_tokens": 59,
  "output_tokens": 26,
  "cache_creation_tokens": 0,
  "cache_read_tokens": 0,
  "cost_usd": 0.000567,
  "latency_ms": 1522.5,
  "formatting": {
    "directive_balance": true,
    "fence_consistency": true,
    "code_block_integrity": true,
    "fullwidth_punctuation": 1.0,
    "directive_spacing": 1.0
  }
}
```

`entry_type`, `domain` and `difficulty` are copied from the dataset entry, so
a run file can be sliced by type or domain on its own, without loading `data/`
alongside it.

The three token counts do not overlap: `input_tokens` is what was billed at the
full input rate, and the two cache counts are what was written to and read from
the prompt cache. The whole prompt is their sum. Both cache fields are zero on
the record above, and on every run recorded before v0.7.0.

`formatting` holds the five automated checks, scored at write time from the
source and the translation. The first three are pass/fail; the last two are
0–1 rates:

| Check | Meaning |
|---|---|
| `directive_balance` | Translation carries the same number of triple-backtick fence markers as the source |
| `fence_consistency` | Math fencing is not mixed — `$$` blocks and `{math}` directive blocks each open and close with their own marker |
| `code_block_integrity` | Contents of fenced code blocks came through unchanged |
| `fullwidth_punctuation` | Share of prose punctuation on Chinese lines that is full-width (`，。！？；：`) rather than ASCII |
| `directive_spacing` | Share of inline `{doc}`/`{ref}`/`{numref}`-style roles that have a space between the preceding Chinese character and the role |

`scripts/analyze_runs.py` aggregates these across runs — it recomputes them
for older records that predate the field, so every run is comparable:

```bash
uv run python scripts/analyze_runs.py                    # all entry types
uv run python scripts/analyze_runs.py --type paragraphs  # one entry type
```

The findings from the runs committed here are written up in
[`results/model-outputs/NOTES.md`](../../../results/model-outputs/NOTES.md) —
worth reading before you spend money on a sweep of your own.

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
- **Check leaderboard**: `qebench stats` shows the XP leaderboard and dataset coverage. Elo ratings are not part of `stats` — they appear in the judge reveal panel, and on the dashboard's Model Ratings section, which `qebench export` recomputes from the committed judgments
- **Add custom prompts**: Create a new `.txt` file in `prompts/` and pass its name with `--prompt`
- **Glossary & prompts**: See [Glossary & Prompt Templates](glossary-and-prompts.md) for details on glossary injection
- **Seed more data**: See [Seeding from Lectures](../../developer/seeding-from-lectures.md) to extract sentence/paragraph pairs (developer guide)
