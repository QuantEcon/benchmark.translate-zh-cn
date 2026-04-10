# Tutorial: Seeding Data from Lectures

This tutorial explains how to use `scripts/seed_from_lectures.py` to
extract aligned English-Chinese sentence and paragraph pairs from QuantEcon
lecture repositories.

## Background

The benchmark needs sentence-level and paragraph-level translation pairs to
evaluate how LLMs handle connected prose — not just isolated terms.
QuantEcon maintains both English and Chinese versions of its lecture repos,
so we can extract aligned pairs automatically.

The seed script reads from three English↔Chinese repo pairs:

| English Repo | Chinese Repo |
|---|---|
| `lecture-python-intro` | `lecture-intro.zh-cn` |
| `lecture-python-programming` | `lecture-python-programming.zh-cn` |
| `lecture-python.myst` | `lecture-python.zh-cn` |

## Prerequisites

You need the lecture repos cloned locally as siblings of the benchmark repo:

```
quantecon/
├── benchmark.translate-zh-cn/     # ← this repo
├── lecture-python-intro/           # English
├── lecture-intro.zh-cn/            # Chinese
├── lecture-python-programming/
├── lecture-python-programming.zh-cn/
├── lecture-python.myst/
└── lecture-python.zh-cn/
```

If you don't have them, clone them:

```bash
cd /path/to/quantecon
git clone https://github.com/QuantEcon/lecture-python-intro.git
git clone https://github.com/QuantEcon/lecture-intro.zh-cn.git
# ... etc.
```

## Running the Script

```bash
cd benchmark.translate-zh-cn
uv run python scripts/seed_from_lectures.py
```

The script outputs:
- `data/sentences/_seed_lectures.json` — curated sentence pairs
- `data/paragraphs/_seed_lectures.json` — curated paragraph pairs

## How It Works

### 1. File Pairing

The script finds `.md` files in each English repo and looks for matching
filenames in the Chinese repo. Files that exist in both repos form a pair.

### 2. Section Alignment

Each file is split into sections at heading boundaries (`## ...`). Sections
are aligned positionally (section 1 → section 1, section 2 → section 2).
This is more robust than matching by heading text, since headings are
translated to Chinese.

### 3. Paragraph Extraction

Within each aligned section, paragraphs are split on blank lines. English
and Chinese paragraphs are compared for structural similarity:

- **Structural markers** — shared math expressions (`$...$`), citations
  (`{cite}`), and inline code (`` `...` ``) validate alignment
- **Length ratio** — plain prose paragraphs use a 0.4–2.0 length ratio
  to catch misalignment
- **Rejection** — if the English paragraph has structural markers but none
  overlap with the Chinese text, the pair is rejected

### 4. Sentence Extraction

Single-paragraph blocks (no newlines within the block) that pass alignment
validation are treated as sentence candidates.

### 5. Quality Curation

The script curates the extracted pairs for quality and diversity:

- **Sentences**: targets 80 entries — 8 per domain across 10 domains
- **Paragraphs**: targets 30 entries — prioritizes paragraphs with math,
  code, directives, and roles

### 6. Domain Classification

Each lecture file is mapped to a domain using `FILENAME_DOMAIN_MAP` at the
top of the script. The 10 domains covered are:

| Domain | Example lectures |
|---|---|
| `dynamic-programming` | short_path.md, optgrowth.md |
| `linear-algebra` | linear_algebra.md, eigen_I.md |
| `probability-statistics` | prob_dist.md, lln_clt.md |
| `optimization` | optgrowth.md, opt_savings.md |
| `economics` | supply_demand.md, cagan_ree.md |
| `finance` | perm_income.md, cons_smooth.md |
| `general` | intro.md, about.md |
| `scientific-computing` | numpy.md, matplotlib.md |
| `python-fundamentals` | functions.md, python_oop.md |
| `time-series` | ar1_processes.md, markov_chains_I.md |

## Output Format

### Sentences

```json
{
  "id": "sent-001",
  "en": "The Bellman equation is a necessary condition for optimality.",
  "zh": "贝尔曼方程是最优性的必要条件。",
  "domain": "dynamic-programming",
  "difficulty": "intermediate",
  "key_terms": [],
  "source": "lecture-python-intro/short_path.md"
}
```

### Paragraphs

```json
{
  "id": "para-001",
  "en": "Consider the following optimization problem...",
  "zh": "考虑以下优化问题...",
  "domain": "optimization",
  "difficulty": "intermediate",
  "key_terms": [],
  "contains_math": true,
  "contains_code": false,
  "contains_directives": false,
  "contains_roles": true,
  "contains_mixed_fencing": false,
  "source": "lecture-python-intro/optgrowth.md"
}
```

Paragraph entries include MyST feature flags that describe the structural
complexity of each paragraph. These flags are used by the automated
formatting validators when scoring LLM translations.

## Customizing the Script

### Adding lecture repos

To extract from additional repos, add entries to the `REPO_PAIRS` list
at the top of the script:

```python
REPO_PAIRS = [
    ("lecture-python-intro", "lecture-intro.zh-cn"),
    ("lecture-python-programming", "lecture-python-programming.zh-cn"),
    ("lecture-python.myst", "lecture-python.zh-cn"),
    # Add more pairs here:
    ("my-english-repo", "my-chinese-repo"),
]
```

### Adding domain mappings

Add filename-to-domain mappings in `FILENAME_DOMAIN_MAP`:

```python
FILENAME_DOMAIN_MAP = {
    # ...existing entries...
    "my_new_lecture.md": "economics",
}
```

Files not in the map default to `"general"`.

### Adjusting targets

The `_curate_sentences()` and `_curate_paragraphs()` functions accept a
`target` parameter:

```python
# In main():
sentences = _curate_sentences(target=120)   # more sentences
paragraphs = _curate_paragraphs(target=50)  # more paragraphs
```

## Validation

After running the script, validate the output:

```bash
uv run qebench validate
```

This checks all data files (including the seed files) against the Pydantic
schemas. You can also run the test suite:

```bash
uv run --extra dev pytest tests/ -v
```

## Next Steps

- [Running LLM Benchmarks](running-llm-benchmarks.md) — translate the seeded entries with LLMs
- [Judging Translations](judging-translations.md) — evaluate LLM translations of sentences/paragraphs
- [Contributing Entries](contributing-entries.md) — add more entries manually via `qebench add`
