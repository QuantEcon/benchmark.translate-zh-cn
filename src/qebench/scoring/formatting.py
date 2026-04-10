"""Formatting fidelity scoring for translated MyST Markdown.

Automated checks that verify structural integrity of LLM translations:
  - Directive balance: open/close pairs match between source and translation
  - Fence consistency: no mixed $$ / ```{math} markers
  - Code block preservation: code blocks unchanged between source and translation
  - Full-width punctuation: zh-cn uses ，。！？ not ,.!?
  - Directive spacing: space between CJK characters and MyST directives
"""

from __future__ import annotations

import re


def check_directive_balance(source: str, translated: str) -> bool:
    """Verify translated text has the same directive open/close pairs as source.

    Counts fenced code blocks (```) in both texts and checks they match.
    """
    source_fences = len(re.findall(r"^```", source, re.MULTILINE))
    translated_fences = len(re.findall(r"^```", translated, re.MULTILINE))
    return source_fences == translated_fences


def check_fence_consistency(translated: str) -> bool:
    """Verify no mixed $$ / ```{math} fence markers in the translation.

    Valid: $$...$$ or ```{math}...```
    Invalid: $$...``` or ```...$$ (mixed markers)
    """
    lines = translated.splitlines()
    in_dollar_math = False
    in_directive_math = False

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("```{math}"):
            if in_dollar_math:
                return False  # opened $$ but closing with ```
            in_directive_math = True
            continue

        if in_directive_math and stripped == "```":
            in_directive_math = False
            continue

        if stripped.startswith("$$") and not in_directive_math:
            if not in_dollar_math:
                # Opening $$
                # Check if it's a single-line $$ expression $$
                if stripped.endswith("$$") and len(stripped) > 2:
                    continue  # single-line, balanced
                in_dollar_math = True
            else:
                in_dollar_math = False
            continue

        # Check for mixed closings
        if in_dollar_math and stripped == "```":
            return False
        if in_directive_math and stripped.startswith("$$"):
            return False

    # Unclosed blocks are also invalid
    return not in_dollar_math and not in_directive_math


def check_code_block_integrity(source: str, translated: str) -> bool:
    """Verify code blocks are preserved verbatim between source and translation.

    Extracts all fenced code block contents from both texts and checks
    they match.  Only checks ``` fenced blocks (not $$ math).
    """
    source_blocks = _extract_code_blocks(source)
    translated_blocks = _extract_code_blocks(translated)
    return source_blocks == translated_blocks


def check_fullwidth_punctuation(text: str) -> float:
    """Score 0-1 for full-width punctuation compliance in zh-cn text.

    Checks that Chinese prose uses full-width punctuation (，。！？；：)
    instead of ASCII equivalents.  Ignores text inside code blocks and
    inline code spans.
    """
    prose = _strip_code_and_math(text)
    if not prose.strip():
        return 1.0

    # Only check lines that contain CJK characters
    cjk_pattern = re.compile(r"[\u4e00-\u9fff]")
    ascii_punct = re.compile(r"[,\.!?;:]")

    total_punct = 0
    fullwidth_punct = 0
    fullwidth_pattern = re.compile(r"[，。！？；：]")

    for line in prose.splitlines():
        if not cjk_pattern.search(line):
            continue
        ascii_count = len(ascii_punct.findall(line))
        fw_count = len(fullwidth_pattern.findall(line))
        total_punct += ascii_count + fw_count
        fullwidth_punct += fw_count

    if total_punct == 0:
        return 1.0
    return fullwidth_punct / total_punct


def check_directive_spacing(text: str) -> float:
    """Score 0-1 for space before MyST directives after CJK characters.

    Checks that CJK text has a space before inline directives like
    {doc}`...`, {ref}`...`, {any}`...`, etc.
    """
    # Pattern: CJK char directly followed by {directive}` (no space)
    bad_pattern = re.compile(r"[\u4e00-\u9fff]\{(doc|ref|any|term|math|numref)\}`")
    # Pattern: CJK char followed by space then {directive}` (correct)
    good_pattern = re.compile(r"[\u4e00-\u9fff] \{(doc|ref|any|term|math|numref)\}`")

    bad_count = len(bad_pattern.findall(text))
    good_count = len(good_pattern.findall(text))

    total = bad_count + good_count
    if total == 0:
        return 1.0
    return good_count / total


def formatting_score(source: str, translated: str) -> dict:
    """Run all formatting checks and return per-check results.

    Returns a dict with boolean/float results for each check.
    """
    return {
        "directive_balance": check_directive_balance(source, translated),
        "fence_consistency": check_fence_consistency(translated),
        "code_block_integrity": check_code_block_integrity(source, translated),
        "fullwidth_punctuation": check_fullwidth_punctuation(translated),
        "directive_spacing": check_directive_spacing(translated),
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_code_blocks(text: str) -> list[str]:
    """Extract contents of fenced code blocks (``` ... ```)."""
    blocks: list[str] = []
    lines = text.splitlines()
    in_block = False
    current: list[str] = []
    fence_marker = ""

    for line in lines:
        stripped = line.strip()
        if not in_block and stripped.startswith("```"):
            in_block = True
            fence_marker = "```"
            current = []
            continue
        if in_block and stripped == fence_marker:
            blocks.append("\n".join(current))
            in_block = False
            current = []
            continue
        if in_block:
            current.append(line)

    return blocks


def _strip_code_and_math(text: str) -> str:
    """Remove code blocks, inline code, and math blocks from text."""
    # Remove fenced code blocks
    result = re.sub(r"```[^\n]*\n.*?```", "", text, flags=re.DOTALL)
    # Remove inline code
    result = re.sub(r"`[^`]+`", "", result)
    # Remove display math
    result = re.sub(r"\$\$.*?\$\$", "", result, flags=re.DOTALL)
    # Remove inline math
    result = re.sub(r"\$[^$]+\$", "", result)
    return result
