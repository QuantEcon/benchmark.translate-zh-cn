#!/usr/bin/env python3
"""Seed sentences and paragraphs from paired English/Chinese lecture repos.

Usage:
    python scripts/seed_from_lectures.py /path/to/quantecon --append
    python scripts/seed_from_lectures.py /path/to/quantecon --overwrite

Scans paired lecture repos (English + zh-cn), extracts aligned prose
paragraphs, and writes seed data to data/sentences/ and data/paragraphs/.

Paragraph alignment: Both repos share identical file names and structural
markers (headings, code blocks, math blocks), so prose paragraphs extracted
by the same algorithm appear at the same indices.

Ids are positional, so a re-run that rewrites a seed file renumbers every
entry in it — and translation attempts, judgments and the repairs made by hand
in #34 are all keyed on the id.  ``--append`` therefore keeps every committed
entry exactly as it stands and only adds new ones after it; the destructive
rewrite needs ``--overwrite`` said out loud.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path

# Repo pairs: (english_repo_name, chinese_repo_name, lectures_subdir)
REPO_PAIRS = [
    ("lecture-python-intro", "lecture-intro.zh-cn", "lectures"),
    ("lecture-python-programming", "lecture-python-programming.zh-cn", "lectures"),
    ("lecture-python.myst", "lecture-python.zh-cn", "lectures"),
]

# Map filenames to domains (best-effort heuristic)
FILENAME_DOMAIN_MAP: dict[str, str] = {
    # dynamic programming
    "short_path": "dynamic-programming",
    "mccall_model": "dynamic-programming",
    "career_choice": "dynamic-programming",
    "jv": "dynamic-programming",
    "optgrowth": "dynamic-programming",
    "ifp": "dynamic-programming",
    "mccall_correlated": "dynamic-programming",
    "mccall_fitted_vfi": "dynamic-programming",
    "wald_friedman": "dynamic-programming",
    "odu": "dynamic-programming",
    "harrison_kreps": "dynamic-programming",
    "lake_model": "dynamic-programming",
    # stochastic processes / probability
    "ar1_processes": "stochastic-processes",
    "markov_chains_I": "stochastic-processes",
    "markov_chains_II": "stochastic-processes",
    "finite_markov": "stochastic-processes",
    "mc_convergence": "stochastic-processes",
    "lln_clt": "probability",
    "prob_meaning": "probability",
    "prob_dist": "probability",
    # linear algebra
    "eigen_I": "linear-algebra",
    "eigen_II": "linear-algebra",
    "linear_algebra": "linear-algebra",
    "svd_intro": "linear-algebra",
    "complex_and_trig": "mathematics",
    # economics / macro / micro
    "supply_demand_multiple_goods": "economics",
    "supply_demand": "economics",
    "cagan_adaptive": "macroeconomics",
    "cagan_ree": "macroeconomics",
    "cobweb": "macroeconomics",
    "commod_price": "economics",
    "cons_smooth": "macroeconomics",
    "business_cycle": "macroeconomics",
    "solow": "macroeconomics",
    "aiyagari": "macroeconomics",
    "lucas_asset_pricing": "finance",
    # statistics / econometrics
    "monte_carlo": "statistics",
    "heavy_tails": "statistics",
    "inequality": "statistics",
    "time_series_with_matrices": "statistics",
    "geom_series": "mathematics",
    # optimization
    "lp_intro": "optimization",
    "opt_savings": "optimization",
    # programming
    "python_by_example": "other",
    "functions": "other",
    "getting_started": "other",
    "debugging": "other",
    "numpy": "other",
    "matplotlib": "other",
    "pandas": "other",
    "scipy": "other",
}

# Maximum paragraph length for sentences (single-sentence paragraphs)
MAX_SENTENCE_LEN = 300
# Min paragraph length for multi-sentence paragraphs
MIN_PARAGRAPH_LEN = 100
# Max paragraph length (avoid huge blocks)
MAX_PARAGRAPH_LEN = 1500


def _extract_sections(md_content: str) -> list[list[str]]:
    """Extract prose paragraphs grouped by heading section.

    Returns a list of sections, where each section is a list of
    prose paragraphs.  Sections are split at heading lines (# ## ###).
    The order is preserved for positional alignment.
    """
    lines = md_content.splitlines()
    sections: list[list[str]] = [[]]  # Start with one section
    current_para: list[str] = []
    in_fence = False
    in_frontmatter = False
    in_math = False

    def _flush() -> None:
        if current_para:
            text = " ".join(current_para).strip()
            if text:
                sections[-1].append(text)
            current_para.clear()

    for i, line in enumerate(lines):
        stripped = line.strip()

        # YAML frontmatter
        if i == 0 and stripped == "---":
            in_frontmatter = True
            continue
        if in_frontmatter:
            if stripped == "---":
                in_frontmatter = False
            continue

        # Fenced code blocks
        if stripped.startswith("```"):
            _flush()
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        # Math blocks
        if stripped.startswith("$$"):
            _flush()
            in_math = not in_math
            continue
        if in_math:
            continue

        # Headings — start new section
        if stripped.startswith("#"):
            _flush()
            sections.append([])
            continue

        # Labels/targets
        if stripped.startswith("(") and stripped.endswith(")="):
            _flush()
            continue

        # HTML
        if stripped.startswith("<") and ">" in stripped:
            _flush()
            continue

        # Blank line
        if not stripped:
            _flush()
            continue

        current_para.append(stripped)

    _flush()
    return sections


def _shared_markers(en_text: str, zh_text: str) -> bool:
    """Check if en/zh paragraphs correspond closely enough to seed as a pair.

    This defers to :func:`qebench.scoring.alignment.check_pair`, the same
    rule that audits the committed dataset and runs in ``qebench validate``,
    so anything seeded here passes that audit by construction and the two
    cannot drift apart.

    An earlier version accepted a pair as soon as it shared *any single*
    math span, citation or inline-code span, which let genuinely different
    blocks through: an English table and an unrelated Chinese sentence that
    both contained ``$x_1$`` passed, and that is how ``para-009`` and seven
    other entries were seeded misaligned.
    """
    from qebench.scoring.alignment import HAS_MARKERS, MIN_LENGTH_RATIO, check_pair

    if not en_text.strip() or not zh_text.strip():
        return False

    if check_pair(en_text, zh_text):
        return False

    # For prose carrying no markers at all, length is the only signal left.
    # The floor is the audit's, not a second opinion: this branch previously
    # demanded 0.4, which rejects the shorter half of the normal
    # English-to-Chinese range and disagreed with what the audit accepts.
    # An upper bound still guards against a zh block that is far too long to
    # be a translation of this en block.
    if not HAS_MARKERS.search(en_text):
        ratio = len(zh_text) / len(en_text)
        return MIN_LENGTH_RATIO <= ratio <= 2.0

    return True


def _detect_features(text: str) -> dict[str, bool]:
    """Detect MyST formatting features in a paragraph."""
    return {
        "contains_math": bool(re.search(r"\$[^$]+\$", text)),
        "contains_code": bool(re.search(r"`[^`]+`", text)),
        "contains_directives": bool(
            re.search(r"\{(doc|ref|any|term|math|numref|eq|cite|download)\}", text)
        ),
        "contains_roles": bool(re.search(r"\{[a-z]+\}`[^`]+`", text)),
    }


def _infer_domain(filename: str) -> str:
    """Infer domain from filename."""
    stem = Path(filename).stem
    return FILENAME_DOMAIN_MAP.get(stem, "economics")


def _is_pure_list(text: str) -> bool:
    """Check if text is just a list of items (not good prose)."""
    lines = text.split(" ")
    bullet_count = sum(1 for w in lines if w.startswith("*") or w.startswith("-"))
    return bullet_count > 2


def _has_cjk(text: str) -> bool:
    """Check if text contains CJK characters."""
    return bool(re.search(r"[\u4e00-\u9fff]", text))


def extract_pairs(
    en_dir: Path, zh_dir: Path, lectures_subdir: str
) -> tuple[list[dict], list[dict]]:
    """Extract sentence and paragraph pairs from paired lecture repos.

    Uses heading-based section alignment: prose paragraphs within
    each heading section are matched by index.  Falls back to
    marker-based validation (_shared_markers) to skip misaligned pairs.

    Returns (sentences, paragraphs) as lists of dicts ready for JSON.
    """
    en_lectures = en_dir / lectures_subdir
    zh_lectures = zh_dir / lectures_subdir

    if not en_lectures.exists() or not zh_lectures.exists():
        print(f"  Skipping: {en_lectures} or {zh_lectures} not found")
        return [], []

    sentences: list[dict] = []
    paragraphs: list[dict] = []

    # Find common markdown files
    en_files = {f.name for f in en_lectures.glob("*.md")}
    zh_files = {f.name for f in zh_lectures.glob("*.md")}
    common = sorted(en_files & zh_files)

    print(f"  Found {len(common)} common files (of {len(en_files)} en, {len(zh_files)} zh)")

    for filename in common:
        en_content = (en_lectures / filename).read_text(encoding="utf-8")
        zh_content = (zh_lectures / filename).read_text(encoding="utf-8")

        en_sections = _extract_sections(en_content)
        zh_sections = _extract_sections(zh_content)

        domain = _infer_domain(filename)
        repo_name = en_dir.name
        source = f"{repo_name}/{lectures_subdir}/{filename}"

        # Skip files where section counts differ significantly
        if abs(len(en_sections) - len(zh_sections)) > max(2, 0.2 * max(len(en_sections), len(zh_sections))):
            continue

        # Match paragraphs within positionally-aligned sections
        n_sections = min(len(en_sections), len(zh_sections))
        for sec_idx in range(n_sections):
            en_paras = en_sections[sec_idx]
            zh_paras = zh_sections[sec_idx]

            n = min(len(en_paras), len(zh_paras))
            for idx in range(n):
                en_text = en_paras[idx]
                zh_text = zh_paras[idx]

                # Validate alignment
                if not _shared_markers(en_text, zh_text):
                    continue

                # Skip if Chinese doesn't have CJK
                if not _has_cjk(zh_text):
                    continue

                # Skip pure lists
                if _is_pure_list(en_text):
                    continue

                # Skip very short paragraphs
                if len(en_text) < 30:
                    continue

                features = _detect_features(en_text)

                # Classify as sentence or paragraph
                if len(en_text) <= MAX_SENTENCE_LEN:
                    sentences.append({
                        "en": en_text,
                        "zh": zh_text,
                        "domain": domain,
                        "difficulty": "intermediate",
                        "key_terms": [],
                        "source": source,
                    })
                elif MIN_PARAGRAPH_LEN <= len(en_text) <= MAX_PARAGRAPH_LEN:
                    paragraphs.append({
                        "en": en_text,
                        "zh": zh_text,
                        "domain": domain,
                        "difficulty": "intermediate",
                        "key_terms": [],
                        "contains_math": features["contains_math"],
                        "contains_code": features["contains_code"],
                        "contains_directives": features["contains_directives"],
                        "contains_roles": features["contains_roles"],
                        "contains_mixed_fencing": False,
                        "source": source,
                    })

    return sentences, paragraphs


def _curate_sentences(
    sentences: list[dict], target: int = 80
) -> list[dict]:
    """Select a diverse, high-quality subset of sentences.

    Strategy:
    - Prefer sentences with technical terms (inline math, code, citations)
    - Ensure domain diversity (at most 15 per domain)
    - Prefer moderate length (60-250 chars)
    - Skip generic/boilerplate sentences
    """
    import random
    random.seed(42)

    # Score each sentence for "interestingness"
    boilerplate_patterns = [
        r"^(Let's|Let us|We (can|will|now|have)|In this|This lecture|Here we|"
        r"Below|Above|The following|See also|Note that|Recall that|As we)",
        r"^(import |from |plt\.|np\.)",
    ]
    boilerplate_re = [re.compile(p, re.IGNORECASE) for p in boilerplate_patterns]

    scored: list[tuple[float, dict]] = []
    for s in sentences:
        en = s["en"]
        score = 0.0

        # Prefer sentences with inline math
        if re.search(r"\$[^$]+\$", en):
            score += 3.0
        # Prefer citations
        if re.search(r"\{cite\}", en):
            score += 2.0
        # Prefer sentences with technical terms (code backticks)
        if re.search(r"`[^`]+`", en):
            score += 1.0
        # Prefer moderate length
        if 60 <= len(en) <= 250:
            score += 1.0
        # Penalize very short
        if len(en) < 50:
            score -= 2.0
        # Penalize boilerplate
        for bp in boilerplate_re:
            if bp.search(en):
                score -= 3.0
                break

        scored.append((score, s))

    # Sort by score descending
    scored.sort(key=lambda x: x[0], reverse=True)

    # Select per-domain, up to `per_domain` each
    per_domain = max(5, target // max(1, len({s["domain"] for _, s in scored})))
    domain_counts: dict[str, int] = {}
    selected: list[dict] = []

    for _score, s in scored:
        dom = s["domain"]
        if domain_counts.get(dom, 0) >= per_domain:
            continue
        domain_counts[dom] = domain_counts.get(dom, 0) + 1
        selected.append(s)
        if len(selected) >= target:
            break

    return selected


# Two extractions of the same passage differ by more than whitespace: upstream
# rewraps lines, renumbers an exercise, tightens a sentence.  Three of the first
# thirteen candidates matched a committed entry at 0.95 or better while nothing
# unrelated came within 0.50, so the gap this sits in is wide.
_DUPLICATE_RATIO = 0.90

# Below this length a high similarity ratio means little — two short strings
# differing in one character clear 0.90 easily.  Shorter text has to match
# exactly.  Every committed paragraph is at least 292 characters, so this only
# constrains sentences, where near-duplicates are correspondingly less likely
# to be the same passage re-extracted.
_MIN_FUZZY_CHARS = 120


def _normalise(text: str) -> str:
    """Collapse whitespace, so a rewrapped paragraph compares equal."""
    return " ".join(text.split())


def _is_duplicate(candidate: dict, against: list[dict]) -> bool:
    """True when *candidate* is another rendering of something in *against*.

    An exact match is not enough on its own: ``para-001`` and the same passage
    re-extracted today differ only in line breaks, and two more of the first
    thirteen candidates differed from a committed entry by a renumbered list
    item.  One of those came from a different source file, so the comparison
    cannot be scoped by source either.
    """
    text = _normalise(candidate["en"])
    for other in against:
        existing = _normalise(other["en"])
        if text == existing:
            return True
        # Length is a cheap gate on the expensive comparison.
        shorter, longer = sorted((len(text), len(existing)))
        if shorter < _MIN_FUZZY_CHARS:
            continue
        if longer and shorter / longer < _DUPLICATE_RATIO:
            continue
        if difflib.SequenceMatcher(None, text, existing).ratio() >= _DUPLICATE_RATIO:
            return True
    return False


def _is_featured(p: dict) -> bool:
    """True when the paragraph carries the MyST structure the checks score."""
    return bool(
        p.get("contains_mixed_fencing", False)
        or p.get("contains_directives", False)
        or p.get("contains_roles", False)
    )


def _paragraph_rank(p: dict) -> tuple:
    """Sort key preferring the MyST features the formatting checks exercise.

    Directives and roles come first because they are what
    ``directive_balance`` and ``directive_spacing`` actually score; the plain
    feature count breaks ties.
    """
    return (
        bool(p.get("contains_mixed_fencing", False)),
        bool(p.get("contains_directives", False)),
        bool(p.get("contains_roles", False)),
        sum(
            [
                p.get("contains_math", False),
                p.get("contains_code", False),
                p.get("contains_directives", False),
                p.get("contains_roles", False),
            ]
        ),
    )


# The extractor's domain heuristic is filename-based and falls back to
# "economics", which takes 155 of the 184 candidates.  Featured candidates are
# concentrated there too, so an uncapped feature-first pass makes every
# addition economics.  Capping additions per domain trades a little of the
# directive share for a set that still spans the corpus.
DEFAULT_MAX_PER_DOMAIN = 5


def _curate_paragraphs(
    paragraphs: list[dict],
    target: int = 30,
    existing: list[dict] | None = None,
    max_per_domain: int = DEFAULT_MAX_PER_DOMAIN,
) -> list[dict]:
    """Select diverse paragraphs prioritizing MyST features.

    Strategy:
    - Prioritize paragraphs with mixed fencing, directives and roles
    - Take one domain at a time in rounds, so no domain crowds the set out
    - Skip paragraphs that are just prose (prefer formatting-rich ones)

    Pass *existing* to extend a committed set: its entries are excluded from
    the candidates, its domains seed the round-robin so a domain already well
    covered waits its turn, and the returned list holds only the new
    selections.  *max_per_domain* bounds how many of those new selections one
    domain may contribute.
    """
    existing = existing or []
    kept: list[dict] = list(existing)
    by_domain: dict[str, list[dict]] = {}
    for p in sorted(paragraphs, key=_paragraph_rank, reverse=True):
        if _is_duplicate(p, kept):
            continue
        kept.append(p)
        by_domain.setdefault(p["domain"], []).append(p)

    # A domain that already carries entries starts that many rounds behind.
    taken: dict[str, int] = {}
    for entry in existing:
        taken[entry["domain"]] = taken.get(entry["domain"], 0) + 1

    # Directives and roles are what the formatting checks actually exercise,
    # and the committed set is short of them — a 100% pass rate over easy
    # prose says little.  Take every domain's featured candidates first, then
    # come back for plain prose, so the weighting does not cost diversity.
    featured = {d: [p for p in ps if _is_featured(p)] for d, ps in by_domain.items()}
    plain = {d: [p for p in ps if not _is_featured(p)] for d, ps in by_domain.items()}

    selected: list[dict] = []
    added: dict[str, int] = {}
    remaining = target - len(existing)
    for pool in (featured, plain):
        while len(selected) < remaining:
            # Least-covered domain first, so the round-robin evens the set out.
            domains = sorted(
                (d for d, ps in pool.items() if ps and added.get(d, 0) < max_per_domain),
                key=lambda d: (taken.get(d, 0), d),
            )
            if not domains:
                break
            for domain in domains:
                if len(selected) >= remaining:
                    break
                selected.append(pool[domain].pop(0))
                taken[domain] = taken.get(domain, 0) + 1
                added[domain] = added.get(domain, 0) + 1

    return selected


def _load_existing(path: Path) -> list[dict]:
    """Read a committed seed file, or an empty list when there is none."""
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _next_id(existing: list[dict], prefix: str) -> int:
    """One past the highest numeric id in *existing*, or 1 when it is empty."""
    highest = 0
    for entry in existing:
        try:
            highest = max(highest, int(str(entry.get("id", "")).rsplit("-", 1)[-1]))
        except ValueError:
            continue
    return highest + 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Seed sentences and paragraphs from paired English/Chinese lecture repos."
    )
    parser.add_argument("base_dir", type=Path, help="Directory holding the paired lecture repos.")
    parser.add_argument(
        "--append",
        action="store_true",
        help="Keep every committed entry and its id, appending only new ones.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Rewrite the seed files from scratch, renumbering every entry.",
    )
    parser.add_argument("--paragraph-target", type=int, default=30, help="Total paragraphs to end up with.")
    parser.add_argument("--sentence-target", type=int, default=80, help="Total sentences to end up with.")
    parser.add_argument(
        "--max-per-domain",
        type=int,
        default=DEFAULT_MAX_PER_DOMAIN,
        help="Cap on how many new paragraphs one domain may contribute.",
    )
    args = parser.parse_args(argv)

    base_dir = args.base_dir
    if not base_dir.exists():
        print(f"Error: {base_dir} not found")
        return 1

    repo_root = Path(__file__).resolve().parent.parent
    sent_path = repo_root / "data" / "sentences" / "_seed_lectures.json"
    para_path = repo_root / "data" / "paragraphs" / "_seed_lectures.json"

    if args.append and args.overwrite:
        print("Error: pass --append or --overwrite, not both")
        return 1
    if not args.append and not args.overwrite and (sent_path.exists() or para_path.exists()):
        # Ids are positional, so a rewrite renumbers entries that judgments,
        # attempts and the #34 repairs are all keyed on.
        print(
            "Error: seed files already exist. Use --append to add to them, "
            "or --overwrite to renumber every entry from scratch."
        )
        return 1

    all_sentences: list[dict] = []
    all_paragraphs: list[dict] = []

    for en_name, zh_name, subdir in REPO_PAIRS:
        en_dir = base_dir / en_name
        zh_dir = base_dir / zh_name

        if not en_dir.exists():
            print(f"Skipping {en_name}: not found at {en_dir}")
            continue
        if not zh_dir.exists():
            print(f"Skipping {zh_name}: not found at {zh_dir}")
            continue

        print(f"\nProcessing {en_name} ↔ {zh_name}...")
        sents, paras = extract_pairs(en_dir, zh_dir, subdir)
        all_sentences.extend(sents)
        all_paragraphs.extend(paras)

    print(f"\nRaw extraction: {len(all_sentences)} sentences, {len(all_paragraphs)} paragraphs")

    existing_sentences = _load_existing(sent_path) if args.append else []
    existing_paragraphs = _load_existing(para_path) if args.append else []

    # Curate to manageable, diverse subsets
    new_sentences = _curate_sentences(all_sentences, target=args.sentence_target - len(existing_sentences))
    new_paragraphs = _curate_paragraphs(
        all_paragraphs,
        target=args.paragraph_target,
        existing=existing_paragraphs,
        max_per_domain=args.max_per_domain,
    )
    if args.append:
        kept = list(existing_sentences)
        deduped = []
        for candidate in new_sentences:
            if _is_duplicate(candidate, kept):
                continue
            kept.append(candidate)
            deduped.append(candidate)
        new_sentences = deduped

    # Assign IDs, continuing past whatever is already committed
    for i, s in enumerate(new_sentences, _next_id(existing_sentences, "sent")):
        s["id"] = f"sent-{i:03d}"

    for i, p in enumerate(new_paragraphs, _next_id(existing_paragraphs, "para")):
        p["id"] = f"para-{i:03d}"

    all_sentences = existing_sentences + new_sentences
    all_paragraphs = existing_paragraphs + new_paragraphs

    # Write output
    sent_path.parent.mkdir(parents=True, exist_ok=True)
    with open(sent_path, "w", encoding="utf-8") as f:
        json.dump(all_sentences, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"\nSentences: {len(all_sentences)} (+{len(new_sentences)}) → {sent_path}")

    para_path.parent.mkdir(parents=True, exist_ok=True)
    with open(para_path, "w", encoding="utf-8") as f:
        json.dump(all_paragraphs, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"Paragraphs: {len(all_paragraphs)} (+{len(new_paragraphs)}) → {para_path}")

    # Domain summary
    from collections import Counter
    sent_domains = Counter(s["domain"] for s in all_sentences)
    para_domains = Counter(p["domain"] for p in all_paragraphs)
    print(f"\nSentence domains: {dict(sent_domains.most_common())}")
    print(f"Paragraph domains: {dict(para_domains.most_common())}")

    # Paragraph feature summary
    if all_paragraphs:
        n_math = sum(1 for p in all_paragraphs if p.get("contains_math"))
        n_code = sum(1 for p in all_paragraphs if p.get("contains_code"))
        n_dir = sum(1 for p in all_paragraphs if p.get("contains_directives"))
        n_role = sum(1 for p in all_paragraphs if p.get("contains_roles"))
        print("\nParagraph features:")
        print(f"  contains_math:       {n_math}")
        print(f"  contains_code:       {n_code}")
        print(f"  contains_directives: {n_dir}")
        print(f"  contains_roles:      {n_role}")
        n_mixed = sum(1 for p in all_paragraphs if p.get("contains_mixed_fencing"))
        print(f"  contains_mixed_fencing: {n_mixed}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
