"""Context sentence extraction from QuantEcon lecture repos.

Scans Markdown files in cloned lecture repositories, splits text into
sentences, and finds sentences that contain a given term.  Up to
MAX_CONTEXTS random sentences are stored per term, providing translators
with real-world usage examples.
"""

from __future__ import annotations

import re
from pathlib import Path

from qebench.models import Term, TermContext

# Maximum context sentences stored per term
MAX_CONTEXTS = 5

# Lecture repos to scan (under QuantEcon GitHub org)
LECTURE_REPOS = [
    "lecture-python-programming",
    "lecture-python-intro",
    "lecture-python.myst",
    "lecture-python-advanced.myst",
]

GITHUB_ORG = "QuantEcon"


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences on period, exclamation, or question mark.

    Preserves sentence boundaries while handling common abbreviations
    (e.g., i.e., Dr., etc.) by requiring sentence-ending punctuation
    to be followed by whitespace and a capital letter or end-of-string.
    """
    # Split on sentence-ending punctuation followed by whitespace+capital or end
    parts = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)
    return [s.strip() for s in parts if s.strip()]


def _extract_prose(md_content: str) -> str:
    """Extract prose text from MyST Markdown, stripping code blocks and directives.

    Removes:
    - Fenced code blocks (``` ... ```)
    - MyST directives ({directive} ... ```)
    - YAML frontmatter (--- ... ---)
    - HTML tags
    - Markdown image/link syntax noise
    - Lines that are purely headings, labels, or targets
    """
    lines = md_content.splitlines()
    result: list[str] = []
    in_fence = False
    in_frontmatter = False
    in_math = False

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
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        # Multi-line math blocks ($$...$$)
        if stripped.startswith("$$"):
            in_math = not in_math
            continue
        if in_math:
            continue

        # Skip headings, labels, targets, and empty lines
        if stripped.startswith("#") or stripped.startswith("(") and stripped.endswith(")="):
            continue
        if not stripped:
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
            result.append(cleaned)

    return " ".join(result)


def find_contexts(term_en: str, lecture_dirs: list[Path]) -> list[TermContext]:
    """Find sentences containing a term across lecture Markdown files.

    Scans all .md files in the given directories, extracts prose text,
    splits into sentences, and returns up to MAX_CONTEXTS random
    sentences that contain the term (case-insensitive, whole-word match).

    Args:
        term_en: English term to search for.
        lecture_dirs: List of paths to cloned lecture repositories.

    Returns:
        List of TermContext objects with matching sentences and source paths.
    """
    # Build a regex for whole-word matching (case-insensitive)
    # Escape regex special chars in the term
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

            prose = _extract_prose(content)
            sentences = _split_sentences(prose)

            for sentence in sentences:
                if pattern.search(sentence):
                    source = f"{repo_name}/{rel}"
                    matches.append(TermContext(text=sentence, source=source))

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
