# Model Output Notes

Generated: 2026-04-06

## Models

| Model | API ID | Input $/MTok | Output $/MTok |
|---|---|---|---|
| Claude Sonnet 4.6 | `claude-sonnet-4-6` | $3.00 | $15.00 |
| Claude Haiku 4.5 | `claude-haiku-4-5-20251001` | $1.00 | $5.00 |

## Runs

Each model was run with two prompt templates against all 314 seed terms.
Batch translation used 10 concurrent workers via `ThreadPoolExecutor`.

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

No OpenAI runs were generated — `OPENAI_API_KEY` was not available. The provider
has been updated to use `gpt-5.4` and `gpt-5.4-mini` for future runs.
