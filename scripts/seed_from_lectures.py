#!/usr/bin/env python3
"""Seed sentences and paragraphs from paired English/Chinese lecture repos.

Usage:
    python scripts/seed_from_lectures.py /path/to/quantecon

Scans paired lecture repos (English + zh-cn), extracts aligned prose
paragraphs, and writes seed data to data/sentences/ and data/paragraphs/.

Paragraph alignment: Both repos share identical file names and structural
markers (headings, code blocks, math blocks), so prose paragraphs extracted
by the same algorithm appear at the same indices.
"""

from __future__ import annotations

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


def _extract_prose_paragraphs(md_content: str) -> list[str]:
    """Extract prose paragraphs from MyST Markdown, preserving inline markup.

    Returns blank-line-delimited prose blocks, skipping:
    - YAML frontmatter
    - Fenced code blocks (``` ... ```)
    - Multi-line math blocks ($$ ... $$)
    - MyST directives (```{...} ... ```)
    - Lines that are purely headings, labels, or targets
    - HTML blocks
    """
    lines = md_content.splitlines()
    current_para: list[str] = []
    paragraphs: list[str] = []
    in_fence = False
    in_frontmatter = False
    in_math = False

    def _flush() -> None:
        if current_para:
            text = " ".join(current_para)
            text = text.strip()
            if text:
                paragraphs.append(text)
            current_para.clear()

    for i, line in enumerate(lines):
        stripped = line.strip()

        # YAML frontmatter at start of file
        if i == 0 and stripped == "---":
            in_frontmatter = True
            continue
        if in_frontmatter:
            if stripped == "---":
                in_frontmatter = False
            continue

        # Fenced code blocks and directives
        if stripped.startswith("```"):
            _flush()
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        # Multi-line math blocks
        if stripped.startswith("$$"):
            _flush()
            in_math = not in_math
            continue
        if in_math:
            continue

        # Skip headings
        if stripped.startswith("#"):
            _flush()
            continue

        # Skip labels/targets like (label_name)=
        if stripped.startswith("(") and stripped.endswith(")="):
            _flush()
            continue

        # Skip MyST index directives and HTML
        if stripped.startswith("<") and ">" in stripped:
            _flush()
            continue

        # Blank line = paragraph boundary
        if not stripped:
            _flush()
            continue

        current_para.append(stripped)

    _flush()
    return paragraphs


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
    """Check if en/zh paragraphs share structural markers (math, citations).

    Returns True if they likely correspond to each other.
    """
    # Extract shared math expressions
    en_math = set(re.findall(r"\$([^$]+)\$", en_text))
    zh_math = set(re.findall(r"\$([^$]+)\$", zh_text))
    if en_math and en_math & zh_math:
        return True

    # Extract shared citations
    en_cite = set(re.findall(r"\{cite\}`([^`]+)`", en_text))
    zh_cite = set(re.findall(r"\{cite\}`([^`]+)`", zh_text))
    if en_cite and en_cite & zh_cite:
        return True

    # Extract shared inline code
    en_code = set(re.findall(r"`([^`]+)`", en_text))
    zh_code = set(re.findall(r"`([^`]+)`", zh_text))
    if en_code and len(en_code & zh_code) >= 1:
        return True

    # If EN has structural markers but none overlap with ZH, reject
    if en_math or en_cite or en_code:
        return False

    # For pure plain prose, use tighter length ratio
    if len(en_text) > 0 and len(zh_text) > 0:
        ratio = len(zh_text) / len(en_text)
        if 0.4 <= ratio <= 2.0:
            return True

    return False


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


def _curate_paragraphs(
    paragraphs: list[dict], target: int = 30
) -> list[dict]:
    """Select diverse paragraphs prioritizing MyST features.

    Strategy:
    - Prioritize paragraphs with math, directives, roles
    - Ensure domain diversity
    - Skip paragraphs that are just prose (prefer formatting-rich ones)
    """
    # Sort: paragraphs with more features first
    def _feature_score(p: dict) -> int:
        return sum([
            p.get("contains_math", False),
            p.get("contains_code", False),
            p.get("contains_directives", False),
            p.get("contains_roles", False),
        ])

    paragraphs.sort(key=_feature_score, reverse=True)

    per_domain = max(3, target // max(1, len({p["domain"] for p in paragraphs})))
    domain_counts: dict[str, int] = {}
    selected: list[dict] = []

    for p in paragraphs:
        dom = p["domain"]
        if domain_counts.get(dom, 0) >= per_domain:
            continue
        domain_counts[dom] = domain_counts.get(dom, 0) + 1
        selected.append(p)
        if len(selected) >= target:
            break

    return selected


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/seed_from_lectures.py /path/to/quantecon")
        sys.exit(1)

    base_dir = Path(sys.argv[1])
    if not base_dir.exists():
        print(f"Error: {base_dir} not found")
        sys.exit(1)

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

    # Curate to manageable, diverse subsets
    all_sentences = _curate_sentences(all_sentences, target=80)
    all_paragraphs = _curate_paragraphs(all_paragraphs, target=30)

    # Assign IDs
    for i, s in enumerate(all_sentences, 1):
        s["id"] = f"sent-{i:03d}"

    for i, p in enumerate(all_paragraphs, 1):
        p["id"] = f"para-{i:03d}"

    # Write output
    repo_root = Path(__file__).resolve().parent.parent

    # Sentences
    sent_dir = repo_root / "data" / "sentences"
    sent_dir.mkdir(parents=True, exist_ok=True)
    sent_path = sent_dir / "_seed_lectures.json"
    with open(sent_path, "w", encoding="utf-8") as f:
        json.dump(all_sentences, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"\nSentences: {len(all_sentences)} → {sent_path}")

    # Paragraphs
    para_dir = repo_root / "data" / "paragraphs"
    para_dir.mkdir(parents=True, exist_ok=True)
    para_path = para_dir / "_seed_lectures.json"
    with open(para_path, "w", encoding="utf-8") as f:
        json.dump(all_paragraphs, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"Paragraphs: {len(all_paragraphs)} → {para_path}")

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
        print(f"\nParagraph features:")
        print(f"  contains_math:       {n_math}")
        print(f"  contains_code:       {n_code}")
        print(f"  contains_directives: {n_dir}")
        print(f"  contains_roles:      {n_role}")


if __name__ == "__main__":
    main()
