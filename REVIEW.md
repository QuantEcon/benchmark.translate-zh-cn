# Benchmark ↔ Action-Translation: Design Review & Gap Analysis

> **Date**: 10 April 2026  
> **Scope**: Deep analysis of `benchmark.translate-zh-cn` (v0.4.0) and `action-translation` (v0.14.1)  
> **Purpose**: Evaluate benchmark design, identify missed opportunities, and ensure the data collected will maximally improve `action-translation` before RA rollout.

---

## Executive Summary

The benchmark project is well-architected with strong foundations: clean data models, interactive CLI, per-user files eliminating merge conflicts, and a solid judging system with Elo ratings. However, the current data collection is **heavily skewed toward term-level entries** (314 terms, ~0 sentences, ~0 paragraphs), which maps to only one of the four translation modes in `action-translation`. Several high-value data types that would directly improve `action-translation` are not yet captured by the benchmark.

**Key findings:**
1. The benchmark collects excellent glossary-level data but misses the **section-level** and **document-level** translation patterns where `action-translation` spends most of its LLM budget
2. No data is collected about **MyST-specific** translation challenges (directives, roles, math fencing, code cell localization) — the area where `action-translation` has the most bugs
3. The feedback loop from benchmark → glossary is designed but not implemented
4. Several low-cost additions to the data model would significantly increase the benchmark's value

---

## 1. What the Benchmark Currently Collects

### 1.1 Data Types

| Level | Target | Current | Coverage |
|---|---|---|---|
| **Terms** | 500 | 314 seeded + RA contributions | 63% |
| **Sentences** | 100 | ~0 published | 0% |
| **Paragraphs** | 30 | ~0 published | 0% |

### 1.2 Collection Mechanisms

| Mechanism | Data Collected | Format |
|---|---|---|
| `qebench translate` | Human translations + confidence + divergence reasoning | JSONL per user |
| `qebench add` | New entries (term/sentence/paragraph) | JSON per user |
| `qebench judge` | Head-to-head accuracy/fluency ratings (0-5) + winner | JSONL per user |
| `qebench run` | LLM batch translations + tokens + cost + latency | JSONL per model×prompt |
| Context enrichment | Usage sentences from 4 lecture repos | Embedded in term data |

### 1.3 Evaluation Layers

1. **Character overlap** (Jaccard similarity) — informational during translate mode
2. **Glossary compliance** — automated fraction of expected terms in output
3. **Reference overlap** — automated character overlap with reference
4. **Human judgment** — accuracy + fluency scores (0-5) + winner selection
5. **Elo ratings** — model skill ranking from pairwise comparisons

---

## 2. How Benchmark Data Maps to Action-Translation

### 2.1 Action-Translation's Four Translation Modes

| Mode | When Used | What It Needs | Benchmark Coverage |
|---|---|---|---|
| **NEW** | New sections added to source | Good zh-cn for fresh English prose | Partial (terms only) |
| **UPDATE** | Existing sections modified | Ability to diff-update translations | **None** |
| **RESYNC** | Drift recovery | Re-align existing translation to source | **None** |
| **FULL** | New files or `init` | Translate complete documents | **None** |

### 2.2 Direct Value of Current Benchmark Data

**High-value for action-translation:**
- **Glossary validation**: The 314 term entries with human-verified translations directly validate the `glossary/zh-cn.json` used in every translation prompt. The NOTES.md already found Haiku hallucinating "Arrow securities" → "箭头证券" instead of "阿罗证券" — exactly the kind of error glossary enforcement prevents.
- **Prompt comparison**: The default vs. academic prompt comparison (87% Sonnet agreement, 75% cross-model) provides evidence for prompt design.
- **Disagreement catalog**: The 100/314 terms where models disagree are prime candidates for glossary enforcement.

**Limited value currently:**
- No sentence/paragraph data means no evaluation of how LLMs handle the **connected prose** that makes up 95% of `action-translation`'s workload.
- No data about MyST formatting preservation, which is `action-translation`'s most fragile area.
- No evaluation of the **update/resync** modes, which are the most complex translation tasks.

### 2.3 The Glossary Feedback Loop

**Current state**: Designed but not implemented.

The benchmark was seeded FROM `action-translation/glossary/zh-cn.json` via `seed_from_glossary.py`. The config even has `glossary_path: null` with a comment "Set to path of action-translation/glossary/zh-cn.json". But there is no mechanism to push validated improvements back.

**What needs to happen:**
1. Terms where multiple human translators agree on a different translation than the glossary → candidate for glossary update
2. Terms where models consistently produce incorrect translations without glossary guidance → need stronger glossary context
3. New terms discovered by RAs during add/translate → candidates for glossary addition
4. The disagreement catalog (100 terms) should be systematically judged to establish ground truth

---

## 3. Missed Opportunities — What Else to Collect

### 3.1 HIGH PRIORITY: Sentence & Paragraph Data from Real Lectures

**Gap**: The sentence and paragraph targets (100 and 30) are at 0%. These are critical because `action-translation` translates sections (## level), not terms.

**Recommendation**: Prioritize populating sentence/paragraph data by extracting from real QuantEcon lectures. The context enrichment system already clones the 4 lecture repos — extend it to extract candidate sentences and paragraphs automatically.

**Specific additions:**
- Extract sentences containing glossary terms (provides term-in-context evaluation)
- Extract paragraphs that mix prose + math (tests LaTeX preservation)
- Extract paragraphs with MyST directives (tests directive preservation)
- Extract paragraphs from sections that were actually translated by `action-translation` so we can compare human benchmark translations against the action's output

### 3.2 HIGH PRIORITY: MyST Formatting Fidelity Evaluation

**Gap**: The benchmark has zero measurement of formatting preservation. This is `action-translation`'s #1 source of bugs (fence marker mixing, heading spacing, directive balance).

**Recommendation**: Add a formatting evaluation dimension to the benchmark — primarily as **automated scoring**, not as a human evaluation task.

#### What's automated vs. what needs humans

MyST structural integrity is a **machine-checkable** property. The question "did the LLM break the directive fencing?" doesn't need a human judge — a parser can answer it. What humans contribute is (a) curating a good test set and (b) evaluating translation *quality* of the prose within MyST-heavy content.

| Task | Who | Gamified? | What they do |
|---|---|---|---|
| **Add** MyST-heavy paragraphs to the dataset | RAs | 15 XP | Curate test cases from lectures — select paragraphs with directives, math, roles |
| **Translate** MyST-heavy paragraphs | RAs | 10 XP | Translate the prose parts, providing reference translations (same as today) |
| **Judge** model translations of MyST paragraphs | RAs | 5 XP | Rate accuracy/fluency as usual — they focus on meaning, not formatting |
| **Validate** structural fidelity of LLM output | Automated | — | `qebench run` post-processing scores each translation for formatting integrity |
| **Display** formatting scores in judge reveal | Automated | — | After RA picks a winner, show "Formatting: ✓ directives balanced, ✗ mixed fence markers" |

**RAs do NOT need to validate MyST syntax manually.** Their role stays focused on translation quality. The formatting fidelity checks run automatically on every `qebench run` output and are displayed as supplementary information in the judge reveal panel (alongside the existing glossary compliance % and reference overlap %).

#### What to collect (paragraphs with MyST features)

1. **Paragraphs with MyST directives** (`{note}`, `{warning}`, `{exercise}`, `{code-cell}`) — test that LLMs preserve directive boundaries
2. **Paragraphs with inline roles** (`{doc}`, `{ref}`, `{math}`) — test that LLMs preserve role syntax and only translate display text
3. **Paragraphs with mixed math** (inline `$...$` and block `$$...$$`) — test the fence marker mixing problem that `action-translation` explicitly warns about
4. **Code cells with comments** — test the code-comments localization rule

#### Implementation

**Data model** — add flags to the Paragraph model:
```python
class Paragraph(BaseModel):
    # ... existing fields ...
    contains_math: bool          # existing
    contains_code: bool          # existing
    contains_directives: bool    # NEW: has MyST directives
    contains_roles: bool         # NEW: has MyST roles  
    contains_mixed_fencing: bool # NEW: has both $$ and ```{math}
```

**Automated scoring** — add to the scoring module:
```python
# scoring/formatting.py
def check_directive_balance(source: str, translated: str) -> bool:
    """Verify translated text has same directive open/close pairs as source."""

def check_fence_consistency(translated: str) -> bool:
    """Verify no mixed $$ / ```{math} fence markers."""

def check_code_block_integrity(source: str, translated: str) -> bool:
    """Verify code blocks are preserved verbatim."""

def formatting_score(source: str, translated: str) -> dict:
    """Run all formatting checks, return per-check results."""
```

**Integration** — hook into existing flows:
- `qebench run`: After each LLM translation, compute `formatting_score()` and append to the JSONL record
- `qebench judge` reveal panel: Show formatting check results alongside glossary compliance %
- `qebench export`: Aggregate formatting pass rates per model for dashboard

### 3.3 HIGH PRIORITY: Section-Level Update Evaluation

**Gap**: `action-translation`'s most complex mode is UPDATE (old English + new English + current translation → updated translation). The benchmark doesn't test this at all.

**Recommendation**: Create an "update translation" task type where:
1. The RA sees the original English, the modified English, and the existing Chinese translation
2. The RA produces the updated Chinese translation
3. This directly mirrors what `action-translation` asks Claude to do
4. Compare human update quality against various LLM results

**Implementation sketch:**
- New entry type: `UpdatePair` with fields: `old_en`, `new_en`, `current_zh`, `reference_updated_zh`
- Source: Git history of lecture repos (find sections that changed between commits)
- New prompt template: `update.txt` matching `action-translation`'s UPDATE prompt
- Judge mode extended to compare update translations

### 3.4 MEDIUM PRIORITY: Prompt Template Testing

**Gap**: The benchmark has 2 prompt templates (default, academic). `action-translation` uses 4 different prompts (NEW, UPDATE, RESYNC, FULL) with complex instructions about MyST preservation, i18n code, glossary usage, and language-specific rules. None of these are tested.

**Recommendation**: Add prompt templates that mirror `action-translation`'s actual prompts.

**Specific templates to add:**
- `prompts/action-new.txt` — mirrors the NEW section prompt from `action-translation/src/translator.ts`
- `prompts/action-update.txt` — mirrors the UPDATE prompt (the most complex one)
- `prompts/action-full.txt` — mirrors the full document prompt
- `prompts/action-with-glossary.txt` — tests how glossary injection affects translation quality

This lets you run `qebench run --prompt action-new` and compare output quality against the current default/academic prompts, directly measuring whether `action-translation`'s prompt engineering is effective.

### 3.5 MEDIUM PRIORITY: Language-Specific Rule Validation

**Gap**: `action-translation` has zh-cn-specific rules (full-width punctuation, space before MyST directives). The benchmark doesn't check compliance.

**Recommendation**: Add automated validators for language rules.

**What to check:**
- Full-width punctuation usage (，：。！？ vs ,.!?)
- Space before MyST directives (the regex `[\u4e00-\u9fff]{doc}` should have a space)
- No ASCII punctuation in Chinese prose (excluding code blocks and URLs)

**Implementation**: Add to the scoring module:
```python
# scoring/formatting.py
def check_fullwidth_punctuation(text: str) -> float:
    """Score 0-1 for full-width punctuation compliance in zh-cn text."""

def check_directive_spacing(text: str) -> float:
    """Score 0-1 for space before MyST directives after CJK characters."""
```

These automated checks can run on every translation (human and LLM) to build a formatting compliance dataset.

### 3.6 MEDIUM PRIORITY: i18n Code Preservation Testing

**Gap**: `action-translation` has a localization rule that injects CJK font configuration into matplotlib code cells and preserves `# i18n` marked lines. The benchmark doesn't test this.

**Recommendation**: Include code-cell-heavy paragraphs in the benchmark and track whether translations preserve i18n code. This is a binary check (preserved or not) and directly addresses a CRITICAL rule in `action-translation`'s prompts.

### 3.7 LOW PRIORITY: Heading Translation Consistency

**Gap**: `action-translation` maintains a heading-map in frontmatter (`translation.headings`) for cross-language section matching. The benchmark doesn't evaluate heading translation quality or consistency.

**Recommendation**: For sentence/paragraph entries that contain headings, track the heading translation separately. This would help validate that the same section heading always gets the same translation — a key requirement for `action-translation`'s section matching.

### 3.8 LOW PRIORITY: Cost-Effectiveness Tracking

**Gap**: The NOTES.md shows that the academic prompt doubles token usage (~17k → ~36k) with similar quality for well-defined terms. This cost data exists for batch runs but isn't aggregated per-domain or per-difficulty.

**Recommendation**: Extend the export/dashboard to show cost-effectiveness:
- Cost per correct translation by domain
- Cost per correct translation by difficulty level
- Token usage patterns by entry type
- Optimal model selection guidance (e.g., "use Haiku for basic terms, Sonnet for advanced")

This directly informs `action-translation`'s model selection (`claude-model` input).

---

## 4. Design Strengths (What's Working Well)

1. **Per-user files**: Eliminates merge conflicts entirely, critical for multi-RA workflow
2. **XP gamification**: Incentivizes consistent contribution (10/translate, 15/add, 5/judge)
3. **Elo ratings**: Principled model comparison that improves with more judgments
4. **Schema versioning**: `cli_version` on every record enables future migrations
5. **Context enrichment**: 100% coverage of usage sentences from actual lectures grounds the data
6. **Direct-to-main push**: Low friction for RAs — no PR overhead for data contributions
7. **CI validation**: Schema checks + pytest on every push protects data integrity
8. **Dashboard**: Visual progress tracking motivates team effort
9. **Consensus detection**: Auto-skip when models agree saves RA time in judging
10. **Divergence reasoning**: Capturing *why* a human translation differs (register, regional, contextual) is uniquely valuable

---

## 5. Design Concerns & Suggestions

### 5.1 Scoring Scale Recently Changed

The scoring scale changed from 1-10 to 0-5 in v0.4.0. The `HumanScores` model and judgment records need to be consistent. Existing judgments from v0.3.0 use 1-10; new ones use 0-5. Verify that analysis code handles both scales correctly (the `cli_version` field supports this, but confirm the scoring/analysis actually normalizes).

### 5.2 Glossary Path is `null` (and the code never reads it)

`config.yaml` has `glossary_path: null`. Investigation reveals this is worse than it appears — **no code anywhere in the codebase actually loads or uses `glossary_path`**. The field sits in config unused. Specifically:

- `dataset.py`'s `load_config()` returns the full YAML dict, but no caller extracts `glossary_path`
- `run.py` only reads `config["language_pair"]` — the glossary is never passed to LLM providers
- `prompts.py` explicitly rejects unknown placeholders like `{glossary}`, so prompts can't reference it
- The provider interface (`base.py`, `claude.py`) has no glossary parameter
- The glossary compliance scorer in `judge.py` works on term data from entries, not from the glossary file

**The glossary compliance scoring shown in judge reveal does work** — but it scores against the `zh` field of linked Term entries, not against the external glossary file. This means it only checks whether the translation contains the expected Chinese term, not whether it follows the broader glossary.

#### Recommendation: Support GitHub URL for always-fresh glossary

Rather than a local file path (which requires the RA to have `action-translation` cloned), use the raw GitHub URL:

```yaml
glossary_path: https://raw.githubusercontent.com/QuantEcon/action-translation/main/glossary/zh-cn.json
```

**Implementation**:
1. Add a `load_glossary()` function in `utils/dataset.py` that:
   - Detects URL vs local path
   - For URLs: `urllib.request.urlopen()` (no extra dependency needed) with a local `.cache/glossary.json` fallback
   - For local paths: read directly
   - Caches to `.cache/glossary.json` so offline/CI still works
   - Returns parsed term list
2. Wire glossary into `qebench run`:
   - Add optional `{glossary}` placeholder support in `prompts.py`
   - Create a `prompts/action-with-glossary.txt` template that includes glossary terms
   - Pass glossary terms to LLM providers for glossary-guided translation
3. Wire glossary into judge reveal:
   - Load glossary once at session start
   - Check model translations against glossary terms (not just entry `.zh` fields)
4. Add `qebench update` glossary refresh:
   - During `qebench update`, re-fetch the glossary URL and update cache
   - This fits naturally since `update` already pulls repos and enriches contexts

### 5.3 Sentence/Paragraph Contribution Friction

Adding sentences and paragraphs via `qebench add` requires typing full Chinese translations of multi-sentence blocks — high friction. Consider:
- Pre-seeding from `lecture-python.zh-cn` (existing human translations in the Chinese lecture repo)
- Extracting aligned section pairs from English/Chinese repos automatically
- Reducing friction by showing reference translations from the Chinese repo

### 5.4 Limited Prompt Diversity

Only 2 prompts (default, academic) exist. As noted in §3.4, adding prompts that mirror `action-translation`'s actual production prompts would make the benchmark directly useful for prompt iteration.

### 5.5 No OpenAI Baseline

OpenAI runs haven't been generated. Having a non-Anthropic baseline is important for ruling out model-family biases. This should be a priority before RA rollout.

### 5.6 Domain Coverage Imbalance

The 14 domains aren't equally represented. The difficulty classification (64 basic / 172 intermediate / 78 advanced) relies on a heuristic script. Consider having RAs validate difficulty during translation sessions.

---

## 6. Gamification Fit: Human Tasks vs Automated Tests

The benchmark's strength is its gamified RA workflow. The improvements proposed in §3 need to be evaluated through this lens: **which tasks are fun/valuable for humans (gamify them) and which are mechanical checks (automate them)?**

### 6.1 What RAs should do (gamified, earns XP)

| Activity | XP | What RA does | Why it needs a human |
|---|---|---|---|
| **Translate** sentences/paragraphs | 10 | Translate prose within MyST-heavy content | Only a bilingual human can judge natural phrasing |
| **Add** MyST-heavy paragraphs | 15 | Curate test cases: select interesting paragraphs from lectures that have directives, math, roles | Human judgment: "this paragraph is a good test case" |
| **Add** sentences with glossary terms | 15 | Find/create sentences where a glossary term appears in context | Human curation of term-in-context pairs |
| **Judge** model translations | 5 | Rate accuracy/fluency, pick winner | Core human evaluation — meaning, naturalness, register |
| **Validate** difficulty levels | 0 (new) | During translate, confirm/override auto-classified difficulty | RAs are closer to the target student audience |

### 6.2 What should be automated (runs in `qebench run` / CI)

| Check | When it runs | What it measures | Feeds back to |
|---|---|---|---|
| **Directive balance** | After `qebench run` | Do translated paragraphs have matching open/close directives? | Model comparison: which model breaks directives less? |
| **Fence consistency** | After `qebench run` | No mixed `$$`/` ```{math}` markers? | Prompt engineering: do production prompts prevent this? |
| **Code block preservation** | After `qebench run` | Are code cells unchanged? | Validates `action-translation`'s "don't translate code" rule |
| **Full-width punctuation** | After `qebench run` | Does zh-cn output use ，。！ not ,.! in prose? | Language rule compliance |
| **Directive spacing** | After `qebench run` | Space between CJK chars and `{doc}`, `{ref}`, etc.? | zh-cn-specific rule compliance |
| **Glossary compliance** | After `qebench run` + in judge reveal | Do translations use glossary-specified terms? | Glossary coverage effectiveness |
| **Reference overlap** | In judge reveal | Character-level Jaccard with reference | Informational for judges |

### 6.3 What stays in the reveal panel (informational, teaches judges)

The judge reveal panel currently shows: model labels, Elo ratings, reference overlap %, glossary compliance %. Extend it with formatting scores:

```
┌─ Result ──────────────────────────────────────────────────┐
│ ✓ Winner: Translation A                                   │
│                                                           │
│ A: claude-sonnet-4-6 (Elo 1532)                          │
│ B: claude-haiku-4-5 (Elo 1468)                           │
│                                                           │
│ Reference overlap:    A 92%  │  B 87%                     │
│ Glossary compliance:  A 100% │  B 75%                     │
│ Formatting:           A ✓✓✓  │  B ✓✓✗ (mixed fencing)    │
│ Punctuation:          A ✓    │  B ✗ (3 ASCII commas)     │
└───────────────────────────────────────────────────────────┘
```

This teaches RAs about formatting quality without asking them to check syntax manually. Over time, judges will learn to associate certain models with formatting problems.

---

### Must Do (Week 1)

| # | Action | Effort | Impact |
|---|---|---|---|
| 1 | **Seed 50+ sentences** from lecture repos using context enrichment infrastructure | Medium | Fills critical gap — terms alone don't test connected prose |
| 2 | **Seed 15+ paragraphs** with math/directives from lecture repos (flag `contains_directives`, `contains_roles`) | Medium | Tests the MyST formatting preservation that `action-translation` struggles with |
| 3 | **Implement glossary loading from GitHub URL** — add `load_glossary()` with URL support + `.cache` fallback, wire into `qebench run` and judge reveal | Medium | Enables always-fresh glossary scoring; unblocks glossary-guided prompt testing |
| 4 | **Run OpenAI benchmarks** to establish cross-provider baseline | Low | Eliminates blind spot in model comparison |

### Should Do (Week 2-3)

| # | Action | Effort | Impact |
|---|---|---|---|
| 5 | **Add automated formatting validators** (`scoring/formatting.py`) — directive balance, fence consistency, punctuation compliance | Medium | Automated checks on every `qebench run` output; displayed in judge reveal panel |
| 6 | **Add action-translation prompt templates** (action-new, action-update, action-with-glossary) | Low | Directly measures whether production prompts are optimal |
| 7 | **Wire glossary into `qebench run` prompts** — add optional `{glossary}` placeholder, create glossary-injected prompt template | Low | Tests whether glossary injection actually improves LLM term accuracy |
| 8 | **Implement glossary sync-back** script (benchmark → glossary) | Medium | Closes the feedback loop — the stated goal of the project |

### Nice to Have (Phase 5+)

| # | Action | Effort | Impact |
|---|---|---|---|
| 9 | **Add UpdatePair entry type** for testing section-update translations | High | Tests `action-translation`'s most complex mode |
| 10 | **Add per-domain Elo breakdowns** to dashboard | Medium | Shows which domains need better prompts/glossary |
| 11 | **Add BLEU/COMET metrics** | Medium | Industry-standard metrics for publishable results |
| 12 | **Add i18n code preservation tests** | Low | Binary check for a critical `action-translation` rule |

---

## 8. The Feedback Loop: Benchmark → Action-Translation

The ultimate goal is a virtuous cycle:

```
action-translation produces translations
        ↓
benchmark evaluates quality (human + automated)
        ↓
findings flow back as improvements:
  ├── Glossary updates (new terms, corrected translations)
  ├── Prompt refinements (better instructions based on failure patterns)  
  ├── Language rules (new zh-cn rules based on systematic errors)
  ├── Model selection guidance (which model for which task)
  └── Localization rules (new rules for code cells, figures, etc.)
        ↓
action-translation produces better translations
        ↓
(repeat)
```

**Currently implemented:** Glossary seeding (benchmark FROM action-translation)  
**Not yet implemented:** Everything flowing back (benchmark TO action-translation)

### Concrete Feedback Channels to Build

1. **Glossary updates**: When ≥3 human translators agree on a term translation that differs from glossary → auto-generate PR to update `action-translation/glossary/zh-cn.json`
2. **New glossary entries**: When RAs add terms via `qebench add` that don't exist in the glossary → propose additions
3. **Error pattern reports**: Aggregate model failures by category (punctuation, fence mixing, term hallucination) → inform prompt engineering
4. **Model recommendation**: Based on Elo + cost data → recommend default model in `action-translation`'s `action.yml`
5. **Language rule proposals**: When punctuation/spacing validators find systematic patterns → propose new rules for `action-translation/src/language-config.ts`

---

## 9. Summary Assessment

| Dimension | Rating | Notes |
|---|---|---|
| **Architecture** | Excellent | Clean separation, extensible, well-tested |
| **RA Workflow** | Excellent | Low friction, gamified, no merge conflicts |
| **Term Coverage** | Good | 314/500 seeded with 100% context coverage |
| **Sentence/Paragraph Coverage** | Critical Gap | 0% — blocks evaluation of connected prose translation |
| **MyST Format Testing** | Critical Gap | No measurement of formatting preservation |
| **Update Mode Testing** | Gap | No evaluation of the most complex translation mode |
| **Glossary Feedback Loop** | Designed, Not Built | Seeding works; reverse flow missing |
| **Prompt Testing** | Limited | 2 generic prompts; production prompts not tested |
| **Model Diversity** | Limited | Claude only; no OpenAI baseline |
| **Automated Quality Checks** | Limited | Only character overlap; no punctuation/formatting validation |
| **Documentation** | Excellent | Thorough tutorials, CLI reference, architecture docs |
| **Dashboard** | Good | Functional with Chart.js; could expand with model comparisons |

**Bottom line**: The benchmark is well-built infrastructure with a data gap. The tooling is ready for RAs — what's needed before rollout is (1) seeding sentences and paragraphs, (2) adding formatting-aware evaluation, and (3) ensuring the collected data has a clear path back to improving `action-translation`.
