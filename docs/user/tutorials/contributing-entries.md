# Tutorial: Contributing Entries

This tutorial shows how to add new terms, sentences, and paragraphs to the
benchmark dataset using `qebench add`.

## Why Contribute?

The dataset starts with 314 terms seeded from the QuantEcon glossary, plus
80 sentences and 17 paragraphs seeded from lecture repos. To build a
comprehensive benchmark, we need:

- **500 terms** across all economics/math domains (314 seeded so far)
- **100 sentences** from real QuantEcon lectures (80 seeded)
- **30 paragraphs** with math, code, and mixed content (17 seeded)

Every entry you add earns **15 XP** and makes the benchmark more useful.

:::{tip}
For bulk seeding of sentences and paragraphs from lecture repos, see
[Seeding from Lectures](../../developer/seeding-from-lectures.md). The `qebench add` command
is best for adding individual, curated entries.
:::

## Before You Start

Pull the latest data so you're working with the current dataset:

```bash
uv run qebench update
```

## Adding a Term

```bash
uv run qebench add
```

Select **term** when prompted, then fill in:

| Field | Example | Notes |
|---|---|---|
| English term | `marginal cost` | The English source term |
| Chinese translation | `边际成本` | The best/most standard translation |
| Domain | `economics` | Pick from the configured domain list |
| Difficulty | `basic` | How hard to translate: basic / intermediate / advanced |
| Alternatives | `边际费用` | Other valid translations (comma-separated) |
| Source | `quantecon/supply-demand` | Where you found this term (optional) |

:::{note}
After you enter the English text, the CLI checks whether an identical entry
already exists in the dataset (case-insensitive). If a duplicate is found,
you'll see the existing entry and be asked "Add anyway?" — the default is
**No** to prevent accidental duplicates.
:::

After filling in the fields, you'll see a preview:

```
╭────── Preview ──────╮
│  ID:         term-315│
│  English:    marginal cost  │
│  Chinese:    边际成本        │
│  Domain:     economics      │
│  Difficulty: basic          │
╰─────────────────────╯
? Save this entry? (Y/n)
```

Confirm to save. Your entry is saved to `data/terms/{your-username}.json` — 
a file dedicated to your contributions. This avoids merge conflicts with
other contributors.

## Adding a Sentence

Select **sentence** when prompted. Sentences are full clauses or statements
extracted from QuantEcon lectures.

Good sentence entries:
- Contain **domain-specific terminology**
- Are **self-contained** (make sense without surrounding context)
- Include a **verified Chinese translation**

**Example:**
- EN: `The Bellman equation is a necessary condition for optimality.`
- ZH: `贝尔曼方程是最优性的必要条件。`

## Adding a Paragraph

Select **paragraph** when prompted. Paragraphs are the most valuable entry type —
they test how well a translator handles connected prose, math notation, and
technical flow.

Additional fields for paragraphs:
- **Contains math?** — Does it include LaTeX/math notation?
- **Contains code?** — Does it include code snippets?
- **Contains directives?** — Does it include MyST directives (`{note}`, `{warning}`, `{code-cell}`, etc.)?
- **Contains roles?** — Does it include MyST roles (`{doc}`, `{ref}`, `{math}`, etc.)?
- **Contains mixed fencing?** — Does it use both `$$` and `` ```{math} `` markers?

These MyST feature flags help the automated formatting validators determine
which checks to run when LLMs translate the paragraph via `qebench run`.

:::{tip}
The best paragraph entries for benchmarking contain a mix of prose and
structural elements (math, directives, code). Look for paragraphs in
QuantEcon lectures that combine explanation with equations or code examples.
:::

:::{note}
Paragraphs cannot be translated via `qebench translate` (the CLI uses
single-line text input). They appear in `qebench judge` (read-only
comparison) and `qebench run` (LLM translation).
:::

## Submitting Your Contributions

After adding entries, push them to GitHub:

```bash
uv run qebench submit
```

This commits your data files and pushes to `main`. The dashboard updates
automatically to reflect the new entries.

## Tips for Good Entries

1. **Use real sources** — pull from QuantEcon lectures, not synthetic text
2. **Verify translations** — only add Chinese translations you're confident about
3. **Tag difficulty accurately** — based on what level of education typically introduces the term:
   - **basic**: terms introduced in high school (GDP, supply, demand)
   - **intermediate**: terms introduced at the undergraduate level (eigenvalue, stochastic)
   - **advanced**: terms introduced at the graduate level (Bellman equation variants, ergodicity)
4. **Include alternatives** — many terms have multiple valid translations
5. **Fill the gaps** — check `qebench stats` to see which domains need more entries

## How Data Is Organized

- **Seed data** (`data/terms/_seed_*.json`) — the initial 314 terms, organized by domain, read-only
- **Your contributions** (`data/terms/{your-username}.json`) — entries you add via `qebench add`
- **All files are loaded together** — `qebench stats` and `qebench translate` see everything

This per-user file model means multiple RAs can work simultaneously without
any merge conflicts.

## Checking Your Work

After adding entries, verify the dataset:

```bash
uv run qebench stats
```

The domain table updates immediately to reflect your additions.
