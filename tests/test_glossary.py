"""Tests for glossary compliance and reference overlap scoring."""

from __future__ import annotations

from qebench.scoring.glossary import glossary_compliance, reference_overlap


class TestGlossaryCompliance:
    def test_all_terms_present(self) -> None:
        text = "贝尔曼方程递归地刻画了价值函数。"
        terms = ["贝尔曼方程", "价值函数"]
        assert glossary_compliance(text, terms) == 1.0

    def test_some_terms_missing(self) -> None:
        text = "贝尔曼方程描述了最优解。"
        terms = ["贝尔曼方程", "价值函数"]
        assert glossary_compliance(text, terms) == 0.5

    def test_no_terms_present(self) -> None:
        text = "这是一段普通文本。"
        terms = ["贝尔曼方程", "价值函数"]
        assert glossary_compliance(text, terms) == 0.0

    def test_empty_terms_returns_one(self) -> None:
        assert glossary_compliance("任何文本", []) == 1.0

    def test_single_term_found(self) -> None:
        text = "通货膨胀率持续上升。"
        assert glossary_compliance(text, ["通货膨胀"]) == 1.0

    def test_single_term_missing(self) -> None:
        text = "价格水平发生了变化。"
        assert glossary_compliance(text, ["通货膨胀"]) == 0.0


class TestReferenceOverlap:
    def test_identical_strings(self) -> None:
        text = "贝尔曼方程递归地刻画了价值函数"
        assert reference_overlap(text, text) == 1.0

    def test_completely_different(self) -> None:
        assert reference_overlap("甲乙丙", "丁戊己") == 0.0

    def test_partial_overlap(self) -> None:
        a = "贝尔曼方程递归地刻画了价值函数"
        b = "贝尔曼方程以递归方式描述了价值函数"
        score = reference_overlap(a, b)
        assert 0.0 < score < 1.0

    def test_both_empty(self) -> None:
        assert reference_overlap("", "") == 1.0

    def test_one_empty(self) -> None:
        assert reference_overlap("", "有内容") == 0.0
        assert reference_overlap("有内容", "") == 0.0

    def test_ignores_punctuation(self) -> None:
        a = "贝尔曼方程。"
        b = "贝尔曼方程"
        assert reference_overlap(a, b) == 1.0

    def test_symmetric(self) -> None:
        a = "通货膨胀率上升"
        b = "通货膨胀持续走高"
        assert reference_overlap(a, b) == reference_overlap(b, a)
