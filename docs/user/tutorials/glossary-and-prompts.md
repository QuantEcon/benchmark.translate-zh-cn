# Tutorial: Glossary & Prompt Templates

This tutorial covers the prompt templates that mirror
[action-translation](https://github.com/QuantEcon/action-translation)'s
production prompts, and how glossary injection works.

## Background

`action-translation` is a GitHub Action that translates QuantEcon lecture
files from English to Chinese. It uses Claude with carefully crafted prompts
that include MyST Markdown preservation rules, language-specific formatting
guidelines, and a glossary of 300+ economics/math terms.

The `action-basic` and `action-new` prompt templates let you benchmark these
production-style prompts against the simpler `default` and `academic` prompts,
measuring whether the extra instructions improve translation quality.

## Available Prompt Templates

| Template | File | Key features |
|---|---|---|
| `default` | `prompts/default.txt` | Minimal — just "translate this" |
| `academic` | `prompts/academic.txt` | Academic register, preserve math/code |
| `action-basic` | `prompts/action-basic.txt` | MyST-aware rules: preserve directives, no mixed fence markers |
| `action-new` | `prompts/action-new.txt` | MyST rules + glossary injection |

## Using Action-Style Prompts

### Without glossary

The `action-basic` prompt adds MyST Markdown-specific instructions without
requiring a glossary:

```bash
uv run qebench run --prompt action-basic --type sentences -n 20
```

This tells the LLM to:
- Preserve all MyST directives and roles
- Keep code blocks and math equations untranslated
- Maintain heading structure
- Never mix fence markers (`$$` vs `` ```{math} ``)

### With glossary

The `action-new` prompt includes all the rules from `action-basic` plus
a `{glossary}` section populated from `action-translation`'s glossary:

```bash
uv run qebench run --prompt action-new --type sentences -n 20
```

When `qebench run` detects the `{glossary}` placeholder in a prompt template,
it automatically:

1. **Loads the glossary** from the URL in `config.yaml` (`glossary_path`)
2. **Caches it locally** in `.cache/glossary.json` for offline use
3. **Formats terms** as `English → Chinese` lines
4. **Injects** the formatted glossary into the prompt

## Glossary Loading

### How it works

The glossary is fetched from `action-translation`'s GitHub repository:

```yaml
# config.yaml
glossary_path: https://raw.githubusercontent.com/QuantEcon/action-translation/main/glossary/zh-cn.json
```

The `load_glossary()` function in `utils/dataset.py`:
- Detects whether `glossary_path` is a URL or a local file path
- For URLs: fetches via `urllib.request` and caches to `.cache/glossary.json`
- For local paths: reads directly
- Falls back to the cached version if the network is unavailable
- Returns a `list[dict]`, where each dict has at least `en` and `zh-cn` keys

### Refreshing the glossary

The glossary is fetched once and cached. To force a refresh:

```python
from qebench.utils.dataset import load_glossary
glossary = load_glossary(force_refresh=True)
```

### Using a local glossary file

If you have `action-translation` cloned locally, you can point to its
glossary file directly:

```yaml
# config.yaml
glossary_path: /path/to/action-translation/glossary/zh-cn.json
```

## Comparing Prompts

The primary use case is comparing prompt effectiveness. Run the same entries
through multiple prompts, then judge the results:

```bash
# Run all 4 prompts on the same 20 sentences
uv run qebench run --prompt default --type sentences -n 20
uv run qebench run --prompt academic --type sentences -n 20
uv run qebench run --prompt action-basic --type sentences -n 20
uv run qebench run --prompt action-new --type sentences -n 20

# Judge the results
uv run qebench judge -n 20
```

The judge reveal panel shows automated formatting scores alongside your
human ratings, so you can see whether the MyST-aware prompts actually
prevent formatting errors.

## Creating Custom Prompts

To create a new prompt template:

1. Create a `.txt` file in the `prompts/` directory
2. Use these placeholders (all required unless noted):
   - `{source_lang}` — source language (e.g., "en")
   - `{target_lang}` — target language (e.g., "zh-cn")
   - `{domain}` — entry domain (e.g., "economics")
   - `{text}` — the text to translate
   - `{glossary}` — *(optional)* glossary terms, auto-populated from config

3. Use double braces `{{...}}` to escape literal braces in your prompt
   (e.g., `{{math}}` renders as `{math}` in the final prompt)

**Example** — a prompt with glossary:

```text
Translate from {source_lang} to {target_lang}.
Domain: {domain}

Use these terms consistently:
{glossary}

Text:
{text}
```

Then use it:

```bash
uv run qebench run --prompt my-custom-prompt -n 10
```

## Next Steps

- [Running LLM Benchmarks](running-llm-benchmarks.md) — full tutorial on `qebench run`
- [Judging Translations](judging-translations.md) — evaluate results with formatting scores
- [Seeding from Lectures](../../developer/seeding-from-lectures.md) — populate sentences/paragraphs for testing (developer guide)
