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
uv run python scripts/seed_from_lectures.py /path/to/quantecon --append
```

The script outputs:
- `data/sentences/_seed_lectures.json` — curated sentence pairs
- `data/paragraphs/_seed_lectures.json` — curated paragraph pairs

### `--append` versus `--overwrite`

Ids are positional: the tenth paragraph in the file is `para-010`. Translation
attempts, judgments and the reference repairs made by hand in #34 are all keyed
on those ids, so rewriting a seed file renumbers entries that other data points
at.

`--append` keeps every committed entry exactly as it stands, byte for byte, and
adds new ones after it with fresh ids. It is what you want for growing the
dataset. `--overwrite` rewrites from scratch and renumbers everything; it is
what you want only for a first seed or a deliberate reset. Running with neither
flag against existing files stops with an error rather than guessing.

```bash
# Grow paragraphs to 40, leaving sentences and every committed id alone
uv run python scripts/seed_from_lectures.py .cache/lectures --append \
    --paragraph-target 40 --sentence-target 80
```

Candidates are compared against the committed set on normalised text and then
on a 0.90 similarity ratio, because upstream rewraps lines and renumbers list
items — three of the first thirteen candidates were re-extractions of a
committed paragraph that an exact-match check let through. Text shorter than
120 characters has to match exactly instead, since a high ratio between two
short strings means little.

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

Within each aligned section, paragraphs are split on blank lines. Every
English/Chinese pair is then checked by `check_pair()` from
`qebench.scoring.alignment`. That module is the single definition of what
makes a pair sound, and all three callers share it — the seeder,
`scripts/audit_alignment.py`, and `qebench validate` — so a pair seeded
here passes the audit by construction and the rules cannot drift apart.

`check_pair()` returns a list of problems, empty when the pair looks sound.
It weighs three signals, each one something a faithful translation
preserves:

- **Math spans** — inline `$...$` is copied verbatim, never translated, so
  most of the English spans should reappear in the Chinese. The pair is
  rejected when more than `MAX_MISSING_MATH` (0.5) of them are missing.
- **Reference targets** — the target of a `{doc}`, `{eq}`, `{ref}`,
  `{numref}`, `{cite}`, `{any}` or `{term}` role is an identifier, so it
  survives translation even though the role's display text does not. Any
  English target missing from the Chinese rejects the pair.
- **Length ratio** — the weakest signal, and used as such, since English is
  often simply more verbose than its translation. The floor is
  `MIN_LENGTH_RATIO` (0.30). It drops to `MIN_LENGTH_RATIO_SUPPORTED`
  (0.20) when the pair carries markers and every one of them carried over,
  because that is direct evidence the two correspond.

For prose carrying no markers at all, length is the only signal left, so
the seeder additionally caps the ratio at 2.0 to reject a Chinese block far
too long to be a translation of its English.

Do not loosen this back into a "shares any marker" test. The rule it
replaced accepted a pair as soon as it shared a *single* math span and
skipped the length check entirely, so an English table and an unrelated
Chinese sentence that both contained `$x_1$` passed. That is how `para-009`
and seven other entries were seeded misaligned (issue #31).

### 4. Sentence Extraction

Pairs that pass alignment validation are classified by the length of the
English side: 300 characters or fewer (`MAX_SENTENCE_LEN`) becomes a
sentence candidate, and anything longer, up to `MAX_PARAGRAPH_LEN` (1500),
becomes a paragraph candidate. The two branches are exclusive, so the
`MIN_PARAGRAPH_LEN` (100) floor never binds. Pairs whose English side is
under 30 characters, whose Chinese side carries no CJK, or that are just
bullet lists are dropped before this point.

### 5. Quality Curation

The script curates the extracted pairs for quality and diversity:

- **Sentences**: targets 80 entries — capped per domain at
  `max(5, target // number of domains present)`, so the mix stays diverse
- **Paragraphs**: targets 30 entries. Paragraphs carrying mixed fencing,
  directives or roles are taken first, because those are what the formatting
  checks actually score and a pass rate over easy prose says little. Selection
  then round-robins across domains, least-covered first, so the weighting does
  not cost diversity, and `--max-per-domain` (default 5) stops one domain
  taking every slot — the filename-based domain heuristic falls back to
  `economics`, which claims 155 of the 184 candidates, so without the cap every
  addition lands there

### 6. Domain Classification

Each lecture file is mapped to a domain using `FILENAME_DOMAIN_MAP` at the
top of the script. The 11 domains covered are:

| Domain | Example lectures |
|---|---|
| `dynamic-programming` | short_path.md, optgrowth.md |
| `stochastic-processes` | ar1_processes.md, markov_chains_I.md |
| `probability` | prob_dist.md, lln_clt.md |
| `statistics` | monte_carlo.md, heavy_tails.md |
| `linear-algebra` | linear_algebra.md, eigen_I.md |
| `mathematics` | complex_and_trig.md, geom_series.md |
| `optimization` | lp_intro.md, opt_savings.md |
| `economics` | supply_demand.md, commod_price.md |
| `macroeconomics` | cagan_ree.md, cons_smooth.md |
| `finance` | lucas_asset_pricing.md |
| `other` | numpy.md, functions.md |

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
  "source": "lecture-python-intro/lectures/short_path.md"
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
  "source": "lecture-python-intro/lectures/lp_intro.md"
}
```

Paragraph entries include MyST feature flags that describe the structural
complexity of each paragraph. These flags can be used for filtering or
analysis when evaluating LLM translations.

## Customizing the Script

### Adding lecture repos

To extract from additional repos, add entries to the `REPO_PAIRS` list
at the top of the script:

```python
REPO_PAIRS = [
    ("lecture-python-intro", "lecture-intro.zh-cn", "lectures"),
    ("lecture-python-programming", "lecture-python-programming.zh-cn", "lectures"),
    ("lecture-python.myst", "lecture-python.zh-cn", "lectures"),
    # Add more pairs here:
    ("my-english-repo", "my-chinese-repo", "lectures"),
]
```

### Adding domain mappings

Add filename-to-domain mappings in `FILENAME_DOMAIN_MAP`. Keys are the
filename *stem* — `_infer_domain()` looks up `Path(filename).stem`, so an
entry keyed with the `.md` extension never matches:

```python
FILENAME_DOMAIN_MAP = {
    # ...existing entries...
    "my_new_lecture": "economics",
}
```

Files not in the map default to `"economics"`.

### Adjusting targets

Targets are command-line arguments, and count the whole set rather than the
addition, so re-running with the same target is a no-op:

```bash
uv run python scripts/seed_from_lectures.py .cache/lectures --append \
    --sentence-target 120 --paragraph-target 50 --max-per-domain 6
```

## Validation

After running the script, validate the output:

```bash
uv run qebench validate
```

This checks all data files (including the seed files) against the Pydantic
schemas, and re-runs the alignment rule from step 3 over every sentence and
paragraph. Alignment problems are reported as warnings, since the rule is a
heuristic; add `--strict` to fail on them instead. To see the offending text
alongside each warning:

```bash
uv run python scripts/audit_alignment.py --show-text
```

You can also run the test suite:

```bash
uv run --extra dev pytest tests/ -v
```

## Next Steps

- [Running LLM Benchmarks](../user/tutorials/running-llm-benchmarks.md) — translate the seeded entries with LLMs
- [Judging Translations](../user/tutorials/judging-translations.md) — evaluate LLM translations of sentences/paragraphs
- [Contributing Entries](../user/tutorials/contributing-entries.md) — add more entries manually via `qebench add`
