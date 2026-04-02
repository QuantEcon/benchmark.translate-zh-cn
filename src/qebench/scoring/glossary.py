"""Glossary compliance and reference overlap scoring.

Two automated metrics for evaluating translation quality:
  - Glossary compliance: checks if known term translations appear in the output
  - Reference overlap: character-level Jaccard similarity with the reference
"""

from __future__ import annotations


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


def reference_overlap(translated: str, reference: str) -> float:
    """Character-level Jaccard similarity between translation and reference.

    Strips common Chinese punctuation and whitespace before comparison.
    Returns a value between 0.0 and 1.0.
    """
    strip_chars = set(" \t\n，。、；：！？（）""''《》【】·—…")
    a_chars = set(translated) - strip_chars
    r_chars = set(reference) - strip_chars

    if not a_chars and not r_chars:
        return 1.0
    if not a_chars or not r_chars:
        return 0.0

    intersection = a_chars & r_chars
    union = a_chars | r_chars
    return len(intersection) / len(union)
