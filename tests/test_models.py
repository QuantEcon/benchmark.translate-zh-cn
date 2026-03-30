"""Tests for Pydantic data models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from qebench.models import Difficulty, HumanScores, Paragraph, Sentence, Term


class TestTerm:
    def test_valid_term(self) -> None:
        t = Term(
            id="term-001",
            en="Bellman equation",
            zh="贝尔曼方程",
            domain="dynamic-programming",
            difficulty=Difficulty.intermediate,
        )
        assert t.id == "term-001"
        assert t.alternatives == []
        assert t.source == ""

    def test_term_with_alternatives(self) -> None:
        t = Term(
            id="term-042",
            en="value function",
            zh="价值函数",
            domain="dynamic-programming",
            difficulty=Difficulty.basic,
            alternatives=["值函数"],
            source="quantecon/dp-intro",
        )
        assert t.alternatives == ["值函数"]

    def test_invalid_id_pattern(self) -> None:
        with pytest.raises(ValidationError, match="String should match pattern"):
            Term(
                id="bad-id",
                en="test",
                zh="测试",
                domain="economics",
                difficulty=Difficulty.basic,
            )

    def test_empty_en_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Term(
                id="term-001",
                en="",
                zh="测试",
                domain="economics",
                difficulty=Difficulty.basic,
            )

    def test_json_schema_generation(self) -> None:
        schema = Term.model_json_schema()
        assert "properties" in schema
        assert "id" in schema["properties"]
        assert "en" in schema["properties"]


class TestSentence:
    def test_valid_sentence(self) -> None:
        s = Sentence(
            id="sent-001",
            en="The Bellman equation characterizes the value function recursively.",
            zh="贝尔曼方程递归地刻画了价值函数。",
            domain="dynamic-programming",
            difficulty=Difficulty.intermediate,
            key_terms=["term-001"],
        )
        assert s.key_terms == ["term-001"]
        assert s.human_scores is None

    def test_sentence_with_scores(self) -> None:
        s = Sentence(
            id="sent-002",
            en="Supply equals demand.",
            zh="供给等于需求。",
            domain="microeconomics",
            difficulty=Difficulty.basic,
            human_scores=HumanScores(accuracy=9, fluency=8),
        )
        assert s.human_scores is not None
        assert s.human_scores.accuracy == 9


class TestParagraph:
    def test_valid_paragraph(self) -> None:
        p = Paragraph(
            id="para-001",
            en="Dynamic programming breaks complex problems into simpler subproblems.",
            zh="动态规划将复杂问题分解为更简单的子问题。",
            domain="dynamic-programming",
            difficulty=Difficulty.intermediate,
            contains_math=True,
            contains_code=False,
        )
        assert p.contains_math is True
        assert p.contains_code is False


class TestHumanScores:
    def test_valid_scores(self) -> None:
        h = HumanScores(accuracy=7, fluency=8)
        assert h.accuracy == 7

    def test_score_out_of_range(self) -> None:
        with pytest.raises(ValidationError):
            HumanScores(accuracy=0, fluency=8)

        with pytest.raises(ValidationError):
            HumanScores(accuracy=5, fluency=11)
