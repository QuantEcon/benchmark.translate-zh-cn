# Model Output Notes

Two rounds of runs are recorded here. The April round covered terms only; the
August round completed the grid across all three entry types and is where the
formatting validators and the `action-*` prompts first had output to score.

Regenerate every table below with:

```bash
uv run python scripts/analyze_runs.py               # all entry types
uv run python scripts/analyze_runs.py -t paragraphs # one entry type
```

## Models

| Model | API ID | Input $/MTok | Output $/MTok |
|---|---|---|---|
| Claude Sonnet 4.6 | `claude-sonnet-4-6` | $3.00 | $15.00 |
| Claude Haiku 4.5 | `claude-haiku-4-5-20251001` | $1.00 | $5.00 |

---

# August 2026 round — full grid

Generated: 2026-08-19

Both models were run against all four prompt templates and all three entry
types: 2 models × 4 prompts × 3 types = 24 runs, 3,288 translations, $10.58
combined. Batch translation used 10 concurrent workers via `ThreadPoolExecutor`.

Every entry type now has model output from two models × four prompts. The
remaining gap in the definition of done is a second *provider* — the OpenAI
baseline is still blocked on `OPENAI_API_KEY`.

## Cost

| Run | Type | Entries | Input tok | Output tok | Cost | Mean latency |
|---|---|---|---|---|---|---|
| Haiku 4.5 / default | terms | 314 | 13,973 | 3,101 | $0.0295 | 854ms |
| Haiku 4.5 / academic | terms | 314 | 32,417 | 3,986 | $0.0523 | 929ms |
| Haiku 4.5 / action-basic | terms | 314 | 76,459 | 68,295 | $0.4179 | 2,474ms |
| Haiku 4.5 / action-new | terms | 314 | 1,646,459 | 3,018 | $1.6615 | 884ms |
| Sonnet 4.6 / default | terms | 314 | 13,973 | 3,017 | $0.0872 | 1,329ms |
| Sonnet 4.6 / academic | terms | 314 | 32,417 | 3,027 | $0.1427 | 1,383ms |
| Sonnet 4.6 / action-basic | terms | 314 | 76,459 | 7,686 | $0.3447 | 1,552ms |
| Sonnet 4.6 / action-new | terms | 314 | 1,646,459 | 3,861 | $4.9973 | 1,485ms |
| Haiku 4.5 / default | sentences | 80 | 6,570 | 4,506 | $0.0291 | 1,129ms |
| Haiku 4.5 / academic | sentences | 80 | 11,298 | 4,555 | $0.0341 | 1,183ms |
| Haiku 4.5 / action-basic | sentences | 80 | 22,490 | 4,560 | $0.0453 | 1,120ms |
| Haiku 4.5 / action-new | sentences | 80 | 422,490 | 4,549 | $0.4452 | 1,176ms |
| Sonnet 4.6 / default | sentences | 80 | 6,570 | 4,577 | $0.0884 | 2,143ms |
| Sonnet 4.6 / academic | sentences | 80 | 11,298 | 4,659 | $0.1038 | 2,054ms |
| Sonnet 4.6 / action-basic | sentences | 80 | 22,490 | 4,722 | $0.1383 | 2,104ms |
| Sonnet 4.6 / action-new | sentences | 80 | 422,490 | 4,533 | $1.3355 | 2,195ms |
| Haiku 4.5 / default | paragraphs | 17 | 2,662 | 2,584 | $0.0156 | 1,714ms |
| Haiku 4.5 / academic | paragraphs | 17 | 3,669 | 2,588 | $0.0166 | 1,698ms |
| Haiku 4.5 / action-basic | paragraphs | 17 | 6,045 | 2,593 | $0.0190 | 1,783ms |
| Haiku 4.5 / action-new | paragraphs | 17 | 91,045 | 2,628 | $0.1042 | 1,764ms |
| Sonnet 4.6 / default | paragraphs | 17 | 2,662 | 2,655 | $0.0478 | 3,252ms |
| Sonnet 4.6 / academic | paragraphs | 17 | 3,669 | 2,651 | $0.0508 | 3,651ms |
| Sonnet 4.6 / action-basic | paragraphs | 17 | 6,045 | 2,652 | $0.0579 | 3,343ms |
| Sonnet 4.6 / action-new | paragraphs | 17 | 91,045 | 2,623 | $0.3125 | 3,341ms |

**The glossary is re-sent on every call.** `action-new` carries the whole
glossary in its `{glossary}` block — about 5,240 input tokens per request. On
terms that is 1.65M input tokens for 314 short translations, making the run
57× the cost of `default` for the same work ($4.9973 vs $0.0872 on Sonnet).
Prompt caching the glossary block would remove almost all of that, and is worth
doing before any larger `action-new` sweep. It matters for
`action-translation` too, which sends the same glossary on every section.

## Formatting fidelity

Pass rate for the three boolean checks, mean score for the two 0-1 checks.
The six April term runs predate the `formatting` field on run records and were
scored retroactively by `analyze_runs.py`; the numbers are directly comparable.

| Run | Type | N | Directive balance | Fence consistency | Code integrity | Full-width punct | Directive spacing |
|---|---|---|---|---|---|---|---|
| Haiku 4.5 / default | terms | 314 | 100.0% | 100.0% | 100.0% | 0.994 | 1.000 |
| Haiku 4.5 / academic | terms | 314 | 100.0% | 100.0% | 100.0% | 1.000 | 1.000 |
| Haiku 4.5 / action-basic | terms | 314 | 97.8% | 100.0% | 99.0% | 0.999 | 1.000 |
| Haiku 4.5 / action-new | terms | 314 | 100.0% | 100.0% | 100.0% | 1.000 | 1.000 |
| Sonnet 4.6 / default | terms | 314 | 100.0% | 100.0% | 100.0% | 1.000 | 1.000 |
| Sonnet 4.6 / academic | terms | 314 | 100.0% | 100.0% | 100.0% | 1.000 | 1.000 |
| Sonnet 4.6 / action-basic | terms | 314 | 99.4% | 100.0% | 99.4% | 1.000 | 1.000 |
| Sonnet 4.6 / action-new | terms | 314 | 100.0% | 100.0% | 100.0% | 1.000 | 1.000 |
| Haiku 4.5 / default | sentences | 80 | 100.0% | 100.0% | 100.0% | 0.988 | 0.950 |
| Haiku 4.5 / academic | sentences | 80 | 100.0% | 100.0% | 100.0% | 0.988 | 0.950 |
| Haiku 4.5 / action-basic | sentences | 80 | 100.0% | 100.0% | 100.0% | 1.000 | 0.950 |
| Haiku 4.5 / action-new | sentences | 80 | 100.0% | 100.0% | 100.0% | 0.988 | 0.950 |
| Sonnet 4.6 / default | sentences | 80 | 100.0% | 100.0% | 100.0% | 0.988 | 0.925 |
| Sonnet 4.6 / academic | sentences | 80 | 100.0% | 100.0% | 100.0% | 0.988 | 0.925 |
| Sonnet 4.6 / action-basic | sentences | 80 | 100.0% | 100.0% | 100.0% | 1.000 | 0.938 |
| Sonnet 4.6 / action-new | sentences | 80 | 100.0% | 100.0% | 100.0% | 0.988 | 0.938 |
| Haiku 4.5 / default | paragraphs | 17 | 100.0% | 100.0% | 100.0% | 0.952 | 0.824 |
| Haiku 4.5 / academic | paragraphs | 17 | 100.0% | 100.0% | 100.0% | 0.967 | 0.882 |
| Haiku 4.5 / action-basic | paragraphs | 17 | 100.0% | 100.0% | 100.0% | 0.946 | 1.000 |
| Haiku 4.5 / action-new | paragraphs | 17 | 100.0% | 100.0% | 100.0% | 0.967 | 1.000 |
| Sonnet 4.6 / default | paragraphs | 17 | 100.0% | 100.0% | 100.0% | 0.976 | 0.941 |
| Sonnet 4.6 / academic | paragraphs | 17 | 100.0% | 100.0% | 100.0% | 0.917 | 0.941 |
| Sonnet 4.6 / action-basic | paragraphs | 17 | 100.0% | 100.0% | 100.0% | 0.976 | 1.000 |
| Sonnet 4.6 / action-new | paragraphs | 17 | 100.0% | 100.0% | 100.0% | 1.000 | 1.000 |

**Nothing breaks MyST structure on paragraphs.** Directive balance, fence
consistency and code-block integrity pass 100% for every model × prompt on all
17 paragraphs. The fence-mixing and directive-breakage failures that
`action-translation` warns about did not occur once. That is a real result, but
a bounded one: 17 paragraphs, none longer than 846 characters, and only six
carry code or directives. It says these prompts are safe at paragraph scale,
not that they are safe at section or document scale — which is where
`action-translation` actually operates and where the failures were observed.
Growing the paragraph set toward the 30-entry target, weighted toward
directive-heavy and mixed-fencing content, is what would make this conclusive.

**The `action-*` prompts do fix directive spacing.** This is the one place a
prompt effect shows clearly. On paragraphs the zh-cn rule "put a space between
a CJK character and an inline `{doc}`/`{eq}` role" goes from 0.824 (Haiku /
default) and 0.941 (Sonnet / default) to a clean 1.000 under both
`action-basic` and `action-new`. The explicit MyST rules block earns its place.

**The only boolean failures are on terms, and only under `action-basic`** — 7
of 314 for Haiku, 2 of 314 for Sonnet. They are a symptom of the verbosity
problem below, not of genuine MyST handling: the model wraps a two-word term in
a fenced code block that the source never had.

## Verbosity — `action-basic` is unsafe on short fragments

Counting records whose translation is more than one non-empty line:

| Run | Type | Multi-line | Share |
|---|---|---|---|
| Haiku 4.5 / action-basic | terms | 134/314 | **42.7%** |
| Haiku 4.5 / academic | terms | 4/314 | 1.3% |
| Haiku 4.5 / default | terms | 2/314 | 0.6% |
| Haiku 4.5 / action-new | terms | 0/314 | **0.0%** |
| Sonnet 4.6 / action-basic | terms | 3/314 | 1.0% |
| Sonnet 4.6 / action-new | terms | 1/314 | 0.3% |

Under `action-basic`, Haiku stops translating and starts *writing documentation*
for 43% of terms. `term-003` "Taylor series" came back as a full lecture page —
`# 泰勒级数` heading, a definition section, the Taylor series formula in `$$`,
and a Maclaurin series section. `term-015` "Adaptive expectations" produced the
same shape. `term-222` "Newton's method" came back as an English paragraph
followed by its Chinese translation.

The cause is framing. `action-basic` opens with "You are translating technical
documentation" and then lists MyST structure rules. Given a bare two-word input
with no glossary to anchor it, the smaller model reads the task as *produce a
documentation page about this*. The output-token column shows it plainly:
68,295 output tokens for Haiku / action-basic / terms against 3,018 for the same
model under `action-new`.

`action-new` is identical except that it injects the glossary — and it removes
the failure completely (0/314). The glossary block is not only a terminology
aid; on short inputs it is what keeps the model in translation mode. Sonnet is
largely immune (1.0%), so this is a small-model failure mode.

**For `action-translation`:** never send a bare fragment through a
documentation-framed prompt without the glossary block, particularly on a Haiku-
class model. This is the strongest prompt-design result in the round.

## Agreement

First-line agreement is a good metric for terms and a poor one for connected
prose — two correct paragraph translations rarely share a first line. On
paragraphs the figures run 0-35% and should not be read as a quality signal.
Sonnet-vs-Haiku first-line agreement on paragraphs is 0% in every pairing.

The terms agreement figures from April are unchanged and remain the useful ones;
see the April section below. Full pairwise tables for all three types come from
`analyze_runs.py`.

## Caveats

- **`check_fullwidth_punctuation` was fixed during this round.** It previously
  counted ordered-list markers, decimal points and URLs as ASCII punctuation
  errors, which scored a correctly-translated numbered paragraph at 0.58. It now
  strips structural and numeric ASCII before scoring. Full-width figures here
  are on the corrected metric and are not comparable with any recorded before
  2026-08-19.
- **Some paragraph and sentence references are misaligned.**
  `scripts/audit_alignment.py` flags 5 of 17 paragraphs and 7 of 80 sentences
  where the `zh` reference is not a translation of the `en` source. `para-007`
  keeps only the first of four list items; `para-009` pairs an English table
  with an unrelated Chinese sentence; `para-014` pairs part **c)** with part
  **d)**. This does not affect the formatting or cost numbers above, which never
  touch the reference. It does affect the `reference_overlap` figure in the
  judge reveal panel and the `reference` field stored on every judgment record.
  It no longer causes bad *matchups*: with eight model × prompt labels now
  covering all 411 entries, `_build_matchups` never has to fall back to pairing
  a model against `human-reference`. Repair the flagged entries before the
  judging sprint so the reveal panel is not teaching judges from a wrong
  reference.

---

# April 2026 round — terms only

Generated: 2026-04-06

Each model was run with two prompt templates against all 314 seed terms.

| Run | Entries | Tokens | Cost | Avg Latency |
|---|---|---|---|---|
| Sonnet 4.6 / default | 314 | 16,990 | $0.087 | 1,329ms |
| Sonnet 4.6 / academic | 314 | 35,444 | $0.143 | 1,383ms |
| Haiku 4.5 / default | 314 | 17,074 | $0.030 | 854ms |
| Haiku 4.5 / academic | 314 | 36,403 | $0.052 | 929ms |

Total: 1,256 translations, ~$0.31 combined cost.

## Agreement

Pairwise first-line agreement rates:

| Pair | Agreement |
|---|---|
| Sonnet default vs Sonnet academic | 275/314 (87%) |
| Haiku default vs Haiku academic | 272/314 (86%) |
| Sonnet default vs Haiku default | 244/314 (77%) |
| Sonnet default vs Haiku academic | 236/314 (75%) |
| Sonnet academic vs Haiku default | 236/314 (75%) |
| Sonnet academic vs Haiku academic | 240/314 (76%) |

All four runs agree on 214/314 terms (68%). Disagreements (100/314) span
terminology choices, transliteration style, and acronym handling.

## Quality Observations

**Sonnet 4.6** — Very clean output. Near-zero verbosity (0-1 multi-line
responses). Translations are concise and use standard academic Chinese
terminology (e.g. 续值 for "continuation value", 阿罗证券 for "Arrow securities").

**Haiku 4.5** — Generally good but with notable issues:

- Adds unsolicited English explanatory notes for acronyms (CCDF: 225 chars,
  SSR: 176 chars in default prompt).
- Academic prompt triggers meta-commentary instead of translations for ambiguous
  terms: `term-080` "Tax farming" produced a 1,974-char essay; `term-236`
  "NBER" and `term-235` "Lecture" output refusal/clarification text.
- Some hallucinations: `term-086` "Arrow securities" → 箭头证券 (literal "arrow")
  instead of the correct 阿罗证券 (transliteration of Kenneth Arrow).

**Prompt effect** — The academic prompt doubles token usage (~17k → ~36k) due to
its longer template. Translation quality is similar for well-defined terms but
diverges on ambiguous/short terms like "Exercise" and "Lecture".

## Notable Disagreements

| Term | Sonnet 4.6 | Haiku 4.5 | Note |
|---|---|---|---|
| Continuation value | 续值 | 继续价值 / 延续价值 | Sonnet uses standard DP terminology |
| Arrow securities | 阿罗证券 | 箭头证券 | Haiku hallucinates literal translation |
| Discount factor | 折现因子 | 折扣因子 | Both acceptable; 折现 more standard in finance |
| Naive expectations | 朴素预期 | 幼稚预期 | Both used in literature |
| Financial repression | 金融抑制 | 金融压制 | 抑制 is the standard term |
| Numeraire | 计价单位 | 计价货币 | 计价单位 is broader and more accurate |

## OpenAI

No OpenAI runs have been generated in either round — `OPENAI_API_KEY` is still
unavailable. The provider is configured for `gpt-5.4` and `gpt-5.4-mini`.
