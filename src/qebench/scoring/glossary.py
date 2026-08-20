"""Glossary compliance and reference overlap scoring.

Two automated metrics for evaluating translation quality:
  - Glossary compliance: checks if known term translations appear in the output
  - Reference overlap: character-level Jaccard similarity with the reference

``glossary_compliance`` only answers "did these translations appear"; deciding
*which* translations a given source should produce is
:func:`expected_translations`, so the dashboard, the sync-back report and any
future caller agree on the question rather than each inventing one.
"""

from __future__ import annotations

import re

# A short headword matches inside unrelated Chinese far too easily, and the
# check is plain containment.  Below this many characters an English headword
# is only used when it *is* the whole source, where there is nothing else the
# translation could be about.
MIN_HEADWORD_CHARS = 5


def glossary_compliance(
    translated: str,
    term_translations: list[str],
) -> float:
    """Check what fraction of expected term translations appear in the text.

    Args:
        translated: The translated text to check.
        term_translations: List of expected Chinese term translations
            (e.g. ["贝尔曼方程", "价值函数"]).

    Returns:
        Fraction between 0.0 and 1.0.  Returns 1.0 if term_translations is empty.
    """
    if not term_translations:
        return 1.0

    found = sum(1 for t in term_translations if t in translated)
    return found / len(term_translations)


def expected_translations(
    source: str,
    glossary: list[dict],
    *,
    target_key: str = "zh-cn",
    min_headword_chars: int = MIN_HEADWORD_CHARS,
) -> list[str]:
    """Glossary translations that a faithful rendering of *source* should contain.

    Two cases, because a term entry and a paragraph are different questions:

    - *source* **is** a headword — the whole entry is that term, so the
      glossary's translation is what the model was expected to produce.  This
      is the term-level case, and it covers all 314 committed terms.
    - *source* **contains** a headword — the term appears inside a sentence or
      paragraph, so its translation should appear inside the output.  Only
      headwords of at least *min_headword_chars* count here, since a short one
      matches unrelated text too readily.

    Args:
        source: The English source text.
        glossary: Glossary entries, each with ``en`` and *target_key*.
        target_key: Key holding the target-language translation.
        min_headword_chars: Shortest headword usable as a substring match.

    Returns:
        Expected translations, deduplicated, in a stable order.  Empty when
        the glossary offers nothing relevant — which
        :func:`glossary_compliance` scores as 1.0, so callers that need to
        distinguish "complied" from "nothing to comply with" must check.
    """
    text = source.strip()
    if not text or not glossary:
        return []

    lowered = text.lower()
    exact: list[str] = []
    contained: list[str] = []
    for entry in glossary:
        headword = str(entry.get("en", "")).strip()
        translation = str(entry.get(target_key, "")).strip()
        if not headword or not translation:
            continue
        if headword.lower() == lowered:
            exact.append(translation)
        elif len(headword) >= min_headword_chars and _contains_headword(lowered, headword.lower()):
            contained.append(translation)

    # An exact match is the whole source; anything merely contained in it is
    # then a fragment of the same term, not a second expectation.
    found = exact or contained
    return list(dict.fromkeys(found))


def _contains_headword(lowered_source: str, lowered_headword: str) -> bool:
    """True when *lowered_headword* appears in *lowered_source* as a whole word."""
    return re.search(rf"(?<![a-z0-9]){re.escape(lowered_headword)}(?![a-z0-9])", lowered_source) is not None


def reference_overlap(translated: str, reference: str) -> float:
    """Character-level Jaccard similarity between translation and reference.

    Strips common Chinese punctuation and whitespace before comparison.
    Returns a value between 0.0 and 1.0.
    """
    strip_chars = set(" \t\n，。、；：！？（）\u201c\u201d\u2018\u2019《》【】·\u2014\u2026\"'")
    a_chars = set(translated) - strip_chars
    r_chars = set(reference) - strip_chars

    if not a_chars and not r_chars:
        return 1.0
    if not a_chars or not r_chars:
        return 0.0

    intersection = a_chars & r_chars
    union = a_chars | r_chars
    return len(intersection) / len(union)
