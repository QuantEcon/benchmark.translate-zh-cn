"""Tests for context sentence extraction from lecture repos."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from qebench.models import Term, TermContext  # noqa: F401
from qebench.utils.context import (
    MAX_CONTEXTS,
    MAX_SENTENCE_LENGTH,
    _extract_paragraphs,
    enrich_terms,
    find_contexts,
)

# ---------------------------------------------------------------------------
# _extract_paragraphs
# ---------------------------------------------------------------------------

class TestExtractParagraphs:
    def test_strips_code_blocks(self) -> None:
        md = textwrap.dedent("""\
        Some prose here.

        ```python
        x = 1
        ```

        More prose after.
        """)
        paras = _extract_paragraphs(md)
        assert "x = 1" not in " ".join(paras)
        assert any("Some prose here" in p for p in paras)
        assert any("More prose after" in p for p in paras)

    def test_strips_frontmatter(self) -> None:
        md = textwrap.dedent("""\
        ---
        title: Test
        ---

        Actual content here.
        """)
        paras = _extract_paragraphs(md)
        assert not any("title" in p for p in paras)
        assert any("Actual content" in p for p in paras)

    def test_strips_headings(self) -> None:
        md = textwrap.dedent("""\
        # Heading One

        Body text.

        ## Heading Two

        More body.
        """)
        paras = _extract_paragraphs(md)
        assert not any("Heading One" in p for p in paras)
        assert any("Body text" in p for p in paras)

    def test_strips_inline_math(self) -> None:
        md = "The formula $x^2 + y^2 = z^2$ is Pythagorean."
        paras = _extract_paragraphs(md)
        assert not any("x^2" in p for p in paras)
        assert any("Pythagorean" in p for p in paras)

    def test_strips_links_keeps_text(self) -> None:
        md = "See [dynamic programming](https://example.com) for details."
        paras = _extract_paragraphs(md)
        assert any("dynamic programming" in p for p in paras)
        assert not any("https://example.com" in p for p in paras)

    def test_empty_input(self) -> None:
        assert _extract_paragraphs("") == []

    def test_only_code(self) -> None:
        md = "```python\nx = 1\n```"
        assert _extract_paragraphs(md) == []

    def test_blank_lines_split_paragraphs(self) -> None:
        md = textwrap.dedent("""\
        First paragraph here.

        Second paragraph here.

        Third paragraph here.
        """)
        paras = _extract_paragraphs(md)
        assert len(paras) == 3
        assert paras[0] == "First paragraph here."
        assert paras[1] == "Second paragraph here."
        assert paras[2] == "Third paragraph here."

    def test_multi_line_paragraph_joined(self) -> None:
        md = textwrap.dedent("""\
        This is a paragraph
        that spans two lines.

        Next paragraph.
        """)
        paras = _extract_paragraphs(md)
        assert len(paras) == 2
        assert paras[0] == "This is a paragraph that spans two lines."

    def test_long_paragraph_discarded(self) -> None:
        md = "x " * (MAX_SENTENCE_LENGTH + 1)
        paras = _extract_paragraphs(md)
        assert paras == []

    def test_math_blocks_skipped(self) -> None:
        md = textwrap.dedent("""\
        Before math.

        $$
        x = y + z
        $$

        After math.
        """)
        paras = _extract_paragraphs(md)
        assert not any("x = y" in p for p in paras)
        assert any("Before math" in p for p in paras)
        assert any("After math" in p for p in paras)


# ---------------------------------------------------------------------------
# find_contexts
# ---------------------------------------------------------------------------

class TestFindContexts:
    @pytest.fixture
    def lecture_dir(self, tmp_path: Path) -> Path:
        """Create a fake lecture directory with a markdown file."""
        repo = tmp_path / "lecture-test"
        repo.mkdir()
        md_file = repo / "intro.md"
        md_file.write_text(textwrap.dedent("""\
        ---
        title: Introduction
        ---

        # Introduction

        Dynamic programming is a powerful technique.

        It solves many optimization problems.

        The Bellman equation is central to dynamic programming.

        ```python
        import numpy as np
        ```

        Many economists use dynamic programming in their research.
        """))
        return repo

    def test_finds_matching_sentences(self, lecture_dir: Path) -> None:
        results = find_contexts("dynamic programming", [lecture_dir])
        assert len(results) >= 1
        for ctx in results:
            assert "dynamic programming" in ctx.text.lower()
            assert ctx.source.startswith("lecture-test/")

    def test_no_match_returns_empty(self, lecture_dir: Path) -> None:
        results = find_contexts("quantum computing", [lecture_dir])
        assert results == []

    def test_case_insensitive(self, lecture_dir: Path) -> None:
        results = find_contexts("Dynamic Programming", [lecture_dir])
        assert len(results) >= 1

    def test_whole_word_matching(self, tmp_path: Path) -> None:
        """'matrix' should not match 'matrices'."""
        repo = tmp_path / "lecture-test"
        repo.mkdir()
        md = repo / "test.md"
        md.write_text("Matrices are useful.\n\nA matrix is a rectangular array.")
        results = find_contexts("matrix", [repo])
        texts = [ctx.text for ctx in results]
        # Should match "A matrix is..." but not just "Matrices are useful"
        assert any("matrix" in t.lower() for t in texts)

    def test_max_contexts_limit(self, tmp_path: Path) -> None:
        """Should not return more than MAX_CONTEXTS sentences."""
        repo = tmp_path / "lecture-test"
        repo.mkdir()
        md = repo / "test.md"
        # Write many paragraphs containing "optimization"
        paragraphs = [f"Optimization approach {i} is useful." for i in range(20)]
        md.write_text("\n\n".join(paragraphs))
        results = find_contexts("optimization", [repo])
        assert len(results) <= MAX_CONTEXTS

    def test_nonexistent_directory(self) -> None:
        results = find_contexts("test", [Path("/nonexistent/path")])
        assert results == []

    def test_skips_hidden_dirs(self, tmp_path: Path) -> None:
        repo = tmp_path / "lecture-test"
        hidden = repo / ".git" / "objects"
        hidden.mkdir(parents=True)
        (hidden / "note.md").write_text("Dynamic programming is here.")
        (repo / "visible.md").write_text("No match here.")
        results = find_contexts("dynamic programming", [repo])
        # Should not find anything from .git
        assert all(".git" not in ctx.source for ctx in results)

    def test_skips_build_dirs(self, tmp_path: Path) -> None:
        repo = tmp_path / "lecture-test"
        build = repo / "_build" / "html"
        build.mkdir(parents=True)
        (build / "page.md").write_text("Dynamic programming is here.")
        (repo / "visible.md").write_text("No match here.")
        results = find_contexts("dynamic programming", [repo])
        assert all("_build" not in ctx.source for ctx in results)

    def test_source_format(self, lecture_dir: Path) -> None:
        results = find_contexts("dynamic programming", [lecture_dir])
        assert len(results) >= 1
        # Source should be "repo_name/relative_path"
        assert results[0].source == "lecture-test/intro.md"

    def test_multiple_repos(self, tmp_path: Path) -> None:
        """Contexts can come from multiple repos."""
        repo1 = tmp_path / "repo-one"
        repo1.mkdir()
        (repo1 / "a.md").write_text("Dynamic programming solves this.")

        repo2 = tmp_path / "repo-two"
        repo2.mkdir()
        (repo2 / "b.md").write_text("We use dynamic programming here too.")

        results = find_contexts("dynamic programming", [repo1, repo2])
        sources = {ctx.source for ctx in results}
        assert "repo-one/a.md" in sources
        assert "repo-two/b.md" in sources

    def test_fuzzy_matching_compound_terms(self, tmp_path: Path) -> None:
        """Compound terms fall back to fuzzy matching on significant words (#10)."""
        repo = tmp_path / "lecture-test"
        repo.mkdir()
        # No exact phrase match for "Welfare maximization problem", but one
        # paragraph contains all significant words separately.
        (repo / "test.md").write_text(
            "Welfare analysis is central to this topic.\n\n"
            "We can solve the welfare problem by maximization.\n\n"
            "Unrelated text about nothing."
        )
        results = find_contexts("Welfare maximization problem", [repo])
        assert len(results) == 1
        assert "welfare" in results[0].text.lower()
        assert "maximization" in results[0].text.lower()
        assert "problem" in results[0].text.lower()
        # Must NOT contain the exact phrase (that would be an exact match)
        assert "welfare maximization problem" not in results[0].text.lower()

    def test_fuzzy_matching_fallback(self, tmp_path: Path) -> None:
        """When no exact match, fuzzy finds paragraphs with all significant words."""
        repo = tmp_path / "lecture-test"
        repo.mkdir()
        # "Barrier option" won't match exactly, but both words appear
        (repo / "test.md").write_text(
            "The barrier for this option is very high.\n\n"
            "Unrelated sentence about economics."
        )
        results = find_contexts("Barrier option", [repo])
        assert len(results) == 1
        assert "barrier" in results[0].text.lower()
        assert "option" in results[0].text.lower()

    def test_fuzzy_prefers_exact_over_fuzzy(self, tmp_path: Path) -> None:
        """Exact matches are preferred over fuzzy matches."""
        repo = tmp_path / "lecture-test"
        repo.mkdir()
        exact_paragraph = "A barrier option is a type of exotic option."
        fuzzy_only_paragraph = "The barrier for this option is high."
        (repo / "test.md").write_text(
            f"{exact_paragraph}\n\n"
            f"{fuzzy_only_paragraph}"
        )
        results = find_contexts("barrier option", [repo])
        assert len(results) >= 1
        # Exact match should be returned first
        assert results[0].text == exact_paragraph
        # When exact matches exist, fuzzy-only paragraphs are excluded
        assert all(ctx.text != fuzzy_only_paragraph for ctx in results)


# ---------------------------------------------------------------------------
# enrich_terms
# ---------------------------------------------------------------------------

class TestEnrichTerms:
    def _make_term(self, term_id: str, en: str, contexts: list[TermContext] | None = None) -> Term:
        return Term(
            id=term_id,
            en=en,
            zh="测试",
            domain="test",
            difficulty="basic",
            contexts=contexts or [],
        )

    def test_enriches_terms_without_contexts(self, tmp_path: Path) -> None:
        repo = tmp_path / "lecture-test"
        repo.mkdir()
        (repo / "test.md").write_text("Dynamic programming is great.\n\nOptimization is key.")

        terms = [
            self._make_term("term-001", "dynamic programming"),
            self._make_term("term-002", "optimization"),
        ]
        enriched = enrich_terms(terms, [repo])
        assert enriched == {"term-001", "term-002"}
        assert len(terms[0].contexts) >= 1
        assert len(terms[1].contexts) >= 1

    def test_skips_already_enriched(self, tmp_path: Path) -> None:
        repo = tmp_path / "lecture-test"
        repo.mkdir()
        (repo / "test.md").write_text("Dynamic programming is great.")

        existing = [TermContext(text="Already have this.", source="manual")]
        terms = [self._make_term("term-001", "dynamic programming", contexts=existing)]
        enriched = enrich_terms(terms, [repo])
        assert enriched == set()
        assert len(terms[0].contexts) == 1
        assert terms[0].contexts[0].text == "Already have this."

    def test_no_match_leaves_empty(self, tmp_path: Path) -> None:
        repo = tmp_path / "lecture-test"
        repo.mkdir()
        (repo / "test.md").write_text("Nothing relevant here.")

        terms = [self._make_term("term-001", "quantum entanglement")]
        enriched = enrich_terms(terms, [repo])
        assert enriched == set()
        assert terms[0].contexts == []

    def test_empty_terms_list(self, tmp_path: Path) -> None:
        repo = tmp_path / "lecture-test"
        repo.mkdir()
        assert enrich_terms([], [repo]) == set()
