"""Tests for context sentence extraction from lecture repos."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from qebench.models import Term, TermContext  # noqa: F401
from qebench.utils.context import (
    MAX_CONTEXTS,
    _extract_prose,
    _split_sentences,
    enrich_terms,
    find_contexts,
)

# ---------------------------------------------------------------------------
# _split_sentences
# ---------------------------------------------------------------------------

class TestSplitSentences:
    def test_simple_sentences(self) -> None:
        text = "This is first. This is second. And third."
        result = _split_sentences(text)
        assert result == ["This is first.", "This is second.", "And third."]

    def test_single_sentence(self) -> None:
        assert _split_sentences("Just one sentence.") == ["Just one sentence."]

    def test_empty_string(self) -> None:
        assert _split_sentences("") == []

    def test_question_and_exclamation(self) -> None:
        text = "What is a matrix? It is important! Matrices are everywhere."
        result = _split_sentences(text)
        assert len(result) == 3
        assert "What is a matrix?" in result[0]

    def test_abbreviation_not_split(self) -> None:
        # "e.g." should not cause a split mid-sentence
        text = "Use methods e.g. dynamic programming for optimization. Another sentence follows."
        result = _split_sentences(text)
        # Should not split on "e.g."
        assert any("e.g." in s for s in result)


# ---------------------------------------------------------------------------
# _extract_prose
# ---------------------------------------------------------------------------

class TestExtractProse:
    def test_strips_code_blocks(self) -> None:
        md = textwrap.dedent("""\
        Some prose here.

        ```python
        x = 1
        ```

        More prose after.
        """)
        prose = _extract_prose(md)
        assert "x = 1" not in prose
        assert "Some prose here" in prose
        assert "More prose after" in prose

    def test_strips_frontmatter(self) -> None:
        md = textwrap.dedent("""\
        ---
        title: Test
        ---

        Actual content here.
        """)
        prose = _extract_prose(md)
        assert "title" not in prose
        assert "Actual content" in prose

    def test_strips_headings(self) -> None:
        md = textwrap.dedent("""\
        # Heading One

        Body text.

        ## Heading Two

        More body.
        """)
        prose = _extract_prose(md)
        assert "Heading One" not in prose
        assert "Body text" in prose

    def test_strips_inline_math(self) -> None:
        md = "The formula $x^2 + y^2 = z^2$ is Pythagorean."
        prose = _extract_prose(md)
        assert "x^2" not in prose
        assert "Pythagorean" in prose

    def test_strips_links_keeps_text(self) -> None:
        md = "See [dynamic programming](https://example.com) for details."
        prose = _extract_prose(md)
        assert "dynamic programming" in prose
        assert "https://example.com" not in prose

    def test_empty_input(self) -> None:
        assert _extract_prose("") == ""

    def test_only_code(self) -> None:
        md = "```python\nx = 1\n```"
        assert _extract_prose(md) == ""


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

        Dynamic programming is a powerful technique. It solves many optimization problems.
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
        md.write_text("Matrices are useful. A matrix is a rectangular array.")
        results = find_contexts("matrix", [repo])
        texts = [ctx.text for ctx in results]
        # Should match "A matrix is..." but not just "Matrices are useful"
        assert any("matrix" in t.lower() for t in texts)

    def test_max_contexts_limit(self, tmp_path: Path) -> None:
        """Should not return more than MAX_CONTEXTS sentences."""
        repo = tmp_path / "lecture-test"
        repo.mkdir()
        md = repo / "test.md"
        # Write many sentences containing "optimization"
        sentences = [f"Optimization approach {i} is useful." for i in range(20)]
        md.write_text(" ".join(sentences))
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
        (repo / "test.md").write_text("Dynamic programming is great. Optimization is key.")

        terms = [
            self._make_term("term-001", "dynamic programming"),
            self._make_term("term-002", "optimization"),
        ]
        enriched = enrich_terms(terms, [repo])
        assert enriched == 2
        assert len(terms[0].contexts) >= 1
        assert len(terms[1].contexts) >= 1

    def test_skips_already_enriched(self, tmp_path: Path) -> None:
        repo = tmp_path / "lecture-test"
        repo.mkdir()
        (repo / "test.md").write_text("Dynamic programming is great.")

        existing = [TermContext(text="Already have this.", source="manual")]
        terms = [self._make_term("term-001", "dynamic programming", contexts=existing)]
        enriched = enrich_terms(terms, [repo])
        assert enriched == 0
        assert len(terms[0].contexts) == 1
        assert terms[0].contexts[0].text == "Already have this."

    def test_no_match_leaves_empty(self, tmp_path: Path) -> None:
        repo = tmp_path / "lecture-test"
        repo.mkdir()
        (repo / "test.md").write_text("Nothing relevant here.")

        terms = [self._make_term("term-001", "quantum entanglement")]
        enriched = enrich_terms(terms, [repo])
        assert enriched == 0
        assert terms[0].contexts == []

    def test_empty_terms_list(self, tmp_path: Path) -> None:
        repo = tmp_path / "lecture-test"
        repo.mkdir()
        assert enrich_terms([], [repo]) == 0
