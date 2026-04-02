"""Context sentence extraction from QuantEcon lecture repos.

Scans Markdown files in cloned lecture repositories, extracts prose
paragraphs, and finds paragraphs that contain a given term.  Up to
MAX_CONTEXTS are stored per term, providing translators with real-world
usage examples.

QuantEcon lectures follow a single-sentence-per-paragraph style, so
each blank-line-delimited prose block is treated as one sentence.
"""

from __future__ import annotations

import re
from pathlib import Path

from qebench.models import Term, TermContext

# Maximum context sentences stored per term
MAX_CONTEXTS = 5

# Discard paragraphs longer than this — they are lists, tables, or
# multi-sentence blocks that slipped through, not clean single sentences.
MAX_SENTENCE_LENGTH = 300

# Lecture repos to scan (under QuantEcon GitHub org)
LECTURE_REPOS = [
    "lecture-python-programming",
    "lecture-python-intro",
    "lecture-python.myst",
    "lecture-python-advanced.myst",
]

GITHUB_ORG = "QuantEcon"


def _extract_paragraphs(md_content: str) -> list[str]:
    """Extract prose paragraphs from MyST Markdown.

    Each blank-line-separated block of prose becomes one entry.
    QuantEcon lectures use single-sentence paragraphs, so each
    returned string is typically one sentence.

    Removes:
    - Fenced code blocks (``` ... ```)
    - MyST directives ({directive} ... ```)
    - YAML frontmatter (--- ... ---)
    - Multi-line math blocks ($$ ... $$)
    - HTML tags
    - Markdown image/link syntax noise
    - Lines that are purely headings, labels, or targets
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
            if len(text) <= MAX_SENTENCE_LENGTH:
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

        # Multi-line math blocks ($$...$$)
        if stripped.startswith("$$"):
            _flush()
            in_math = not in_math
            continue
        if in_math:
            continue

        # Skip headings, labels, targets
        if stripped.startswith("#") or stripped.startswith("(") and stripped.endswith(")="):
            _flush()
            continue

        # Blank line = paragraph boundary
        if not stripped:
            _flush()
            continue

        # Strip inline math notation for matching (keep prose around it)
        cleaned = re.sub(r'\$[^$]+\$', '', stripped)
        # Strip image/link references
        cleaned = re.sub(r'!\[.*?\]\(.*?\)', '', cleaned)
        cleaned = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', cleaned)
        # Strip HTML tags
        cleaned = re.sub(r'<[^>]+>', '', cleaned)
        cleaned = cleaned.strip()

        if cleaned:
            current_para.append(cleaned)

    _flush()
    return paragraphs


def find_contexts(term_en: str, lecture_dirs: list[Path]) -> list[TermContext]:
    """Find paragraphs containing a term across lecture Markdown files.

    Scans all .md files in the given directories, extracts prose
    paragraphs, and returns up to MAX_CONTEXTS paragraphs that contain
    the term (case-insensitive, whole-word match).

    Args:
        term_en: English term to search for.
        lecture_dirs: List of paths to cloned lecture repositories.

    Returns:
        List of TermContext objects with matching paragraphs and source paths.
    """
    # Build a regex for whole-word matching (case-insensitive)
    pattern = re.compile(
        r'\b' + re.escape(term_en) + r'\b',
        re.IGNORECASE,
    )

    matches: list[TermContext] = []

    for lecture_dir in lecture_dirs:
        if not lecture_dir.is_dir():
            continue
        repo_name = lecture_dir.name
        for md_path in sorted(lecture_dir.rglob("*.md")):
            # Skip hidden dirs and build artefacts
            rel = md_path.relative_to(lecture_dir)
            if any(part.startswith(".") or part == "_build" for part in rel.parts):
                continue

            try:
                content = md_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            paragraphs = _extract_paragraphs(content)

            for para in paragraphs:
                if pattern.search(para):
                    source = f"{repo_name}/{rel}"
                    matches.append(TermContext(text=para, source=source))

    if not matches:
        return []

    # Deterministic selection: sort by (source, text) for stable output,
    # then take first MAX_CONTEXTS.  Randomness is only at display time.
    matches.sort(key=lambda ctx: (ctx.source, ctx.text))
    return matches[:MAX_CONTEXTS]


def enrich_terms(terms: list[Term], lecture_dirs: list[Path]) -> set[str]:
    """Add context sentences to terms that don't have them yet.

    Modifies terms in-place. Returns the set of enriched term IDs.
    """
    enriched_ids: set[str] = set()
    for term in terms:
        if term.contexts:
            continue
        contexts = find_contexts(term.en, lecture_dirs)
        if contexts:
            term.contexts = contexts
            enriched_ids.add(term.id)
    return enriched_ids
