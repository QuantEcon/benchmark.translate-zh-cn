"""Tests for TermContext model in models.py."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from qebench.models import Term, TermContext


class TestTermContext:
    def test_valid_context(self) -> None:
        ctx = TermContext(text="Dynamic programming is used here.", source="lecture/intro.md")
        assert ctx.text == "Dynamic programming is used here."
        assert ctx.source == "lecture/intro.md"

    def test_empty_text_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TermContext(text="", source="test")

    def test_source_defaults_empty(self) -> None:
        ctx = TermContext(text="Some text.")
        assert ctx.source == ""

    def test_serialization_roundtrip(self) -> None:
        ctx = TermContext(text="Example sentence.", source="repo/file.md")
        data = ctx.model_dump()
        restored = TermContext.model_validate(data)
        assert restored == ctx


class TestTermWithContexts:
    def test_term_with_contexts(self) -> None:
        term = Term(
            id="term-001",
            en="dynamic programming",
            zh="动态规划",
            domain="optimization",
            difficulty="intermediate",
            contexts=[
                TermContext(text="Use dynamic programming here.", source="test.md"),
            ],
        )
        assert len(term.contexts) == 1
        assert term.contexts[0].text == "Use dynamic programming here."

    def test_term_without_contexts_defaults_empty(self) -> None:
        term = Term(
            id="term-001",
            en="test",
            zh="测试",
            domain="test",
            difficulty="basic",
        )
        assert term.contexts == []

    def test_backward_compatible_json(self) -> None:
        """JSON without 'contexts' field should load fine."""
        data = {
            "id": "term-001",
            "en": "test",
            "zh": "测试",
            "domain": "test",
            "difficulty": "basic",
            "alternatives": [],
            "source": "glossary",
        }
        term = Term.model_validate(data)
        assert term.contexts == []

    def test_serialization_includes_contexts(self) -> None:
        term = Term(
            id="term-001",
            en="test",
            zh="测试",
            domain="test",
            difficulty="basic",
            contexts=[TermContext(text="Example.", source="src.md")],
        )
        data = term.model_dump()
        assert "contexts" in data
        assert len(data["contexts"]) == 1
        assert data["contexts"][0]["text"] == "Example."
