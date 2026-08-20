"""Tests for glossary compliance and reference overlap scoring."""

from __future__ import annotations

from qebench.scoring.glossary import expected_translations, glossary_compliance, reference_overlap


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


class TestExpectedTranslations:
    """Which glossary translations a faithful rendering of a source should carry."""

    GLOSSARY = [
        {"en": "Bellman equation", "zh-cn": "贝尔曼方程"},
        {"en": "Adaptive expectations", "zh-cn": "适应性预期"},
        {"en": "Value function", "zh-cn": "价值函数"},
        {"en": "GDP", "zh-cn": "国内生产总值"},
    ]

    def test_a_source_that_is_a_headword(self) -> None:
        assert expected_translations("Bellman equation", self.GLOSSARY) == ["贝尔曼方程"]

    def test_matching_is_case_and_whitespace_insensitive(self) -> None:
        assert expected_translations("  bellman EQUATION  ", self.GLOSSARY) == ["贝尔曼方程"]

    def test_a_headword_inside_a_sentence(self) -> None:
        source = "We assume an adaptive expectations scheme throughout this section."

        assert expected_translations(source, self.GLOSSARY) == ["适应性预期"]

    def test_several_headwords_in_one_source(self) -> None:
        source = "The Bellman equation defines the value function recursively."

        assert set(expected_translations(source, self.GLOSSARY)) == {"贝尔曼方程", "价值函数"}

    def test_a_short_headword_is_not_matched_as_a_substring(self) -> None:
        """`GDP` inside a longer source would match far too readily."""
        source = "Real GDP growth slowed over the period under consideration."

        assert expected_translations(source, self.GLOSSARY) == []

    def test_a_short_headword_still_counts_when_it_is_the_whole_source(self) -> None:
        assert expected_translations("GDP", self.GLOSSARY) == ["国内生产总值"]

    def test_partial_words_do_not_match(self) -> None:
        """`value function` must not fire on `undervalue functionally`."""
        source = "They undervalue functionally equivalent approaches to the problem."

        assert expected_translations(source, self.GLOSSARY) == []

    def test_an_exact_match_suppresses_contained_ones(self) -> None:
        """The whole source is the term; a fragment of it is not a second one."""
        glossary = [
            {"en": "Bellman equation", "zh-cn": "贝尔曼方程"},
            {"en": "Bellman", "zh-cn": "贝尔曼"},
        ]

        assert expected_translations("Bellman equation", glossary) == ["贝尔曼方程"]

    def test_duplicate_translations_are_collapsed(self) -> None:
        glossary = [
            {"en": "Value function", "zh-cn": "价值函数"},
            {"en": "Continuation value", "zh-cn": "价值函数"},
        ]
        source = "The value function and the continuation value coincide here."

        assert expected_translations(source, glossary) == ["价值函数"]

    def test_no_glossary_expects_nothing(self) -> None:
        assert expected_translations("Bellman equation", []) == []

    def test_empty_source_expects_nothing(self) -> None:
        assert expected_translations("   ", self.GLOSSARY) == []

    def test_entries_missing_a_translation_are_skipped(self) -> None:
        glossary = [{"en": "Bellman equation", "zh-cn": ""}, {"en": "", "zh-cn": "空"}]

        assert expected_translations("Bellman equation", glossary) == []

    def test_the_target_key_is_configurable(self) -> None:
        glossary = [{"en": "Bellman equation", "es": "ecuación de Bellman"}]

        assert expected_translations("Bellman equation", glossary, target_key="es") == ["ecuación de Bellman"]

    def test_it_feeds_glossary_compliance(self) -> None:
        expected = expected_translations("Bellman equation", self.GLOSSARY)

        assert glossary_compliance("贝尔曼方程", expected) == 1.0
        assert glossary_compliance("贝尔曼等式", expected) == 0.0
