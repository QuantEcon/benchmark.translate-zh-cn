"""Tests for MyST formatting fidelity scoring."""

from __future__ import annotations

from qebench.scoring.formatting import (
    check_code_block_integrity,
    check_directive_balance,
    check_directive_spacing,
    check_fence_consistency,
    check_fullwidth_punctuation,
    formatting_score,
)


class TestDirectiveBalance:
    def test_balanced(self) -> None:
        source = "```{note}\nSome text\n```"
        translated = "```{note}\n一些文本\n```"
        assert check_directive_balance(source, translated) is True

    def test_unbalanced_missing_close(self) -> None:
        source = "```{note}\nSome text\n```"
        translated = "```{note}\n一些文本"
        assert check_directive_balance(source, translated) is False

    def test_no_directives(self) -> None:
        assert check_directive_balance("plain text", "纯文本") is True

    def test_multiple_directives(self) -> None:
        source = "```{note}\nA\n```\n\n```{warning}\nB\n```"
        translated = "```{note}\nA翻译\n```\n\n```{warning}\nB翻译\n```"
        assert check_directive_balance(source, translated) is True


class TestFenceConsistency:
    def test_valid_dollar_math(self) -> None:
        text = "Some text\n$$\nx^2 + y^2 = z^2\n$$\nMore text"
        assert check_fence_consistency(text) is True

    def test_valid_directive_math(self) -> None:
        text = "Some text\n```{math}\nx^2\n```\nMore text"
        assert check_fence_consistency(text) is True

    def test_mixed_open_dollar_close_backtick(self) -> None:
        text = "$$\nx^2\n```"
        assert check_fence_consistency(text) is False

    def test_single_line_dollar_math(self) -> None:
        text = "$$x^2 + y^2 = z^2$$"
        assert check_fence_consistency(text) is True

    def test_no_math(self) -> None:
        assert check_fence_consistency("plain text") is True

    def test_unclosed_dollar_math(self) -> None:
        text = "$$\nx^2"
        assert check_fence_consistency(text) is False


class TestCodeBlockIntegrity:
    def test_preserved(self) -> None:
        code = "```python\nx = 1\nprint(x)\n```"
        source = f"Some text\n{code}\nMore text"
        translated = f"一些文本\n{code}\n更多文本"
        assert check_code_block_integrity(source, translated) is True

    def test_code_modified(self) -> None:
        source = "```python\nx = 1\n```"
        translated = "```python\nx = 2\n```"
        assert check_code_block_integrity(source, translated) is False

    def test_no_code(self) -> None:
        assert check_code_block_integrity("text", "文本") is True

    def test_code_removed(self) -> None:
        source = "text\n```python\nx = 1\n```"
        translated = "文本"
        assert check_code_block_integrity(source, translated) is False


class TestFullwidthPunctuation:
    def test_all_fullwidth(self) -> None:
        text = "这是一个测试，包含全角标点。请看这里！"
        assert check_fullwidth_punctuation(text) == 1.0

    def test_all_ascii(self) -> None:
        text = "这是一个测试,包含半角标点.请看这里!"
        assert check_fullwidth_punctuation(text) == 0.0

    def test_mixed(self) -> None:
        text = "这是一个测试，包含混合标点.请看这里！"
        score = check_fullwidth_punctuation(text)
        assert 0.0 < score < 1.0

    def test_no_cjk(self) -> None:
        text = "This is English text, with ASCII punctuation."
        assert check_fullwidth_punctuation(text) == 1.0

    def test_empty(self) -> None:
        assert check_fullwidth_punctuation("") == 1.0

    def test_no_punctuation(self) -> None:
        text = "这是一个没有标点的文本"
        assert check_fullwidth_punctuation(text) == 1.0

    def test_inline_ordered_list_markers_ignored(self) -> None:
        """Regression: MyST numbered lists made correct prose score 0.58."""
        text = "1. 以先验开始当前时期。 1. 观测当前测量值。"
        assert check_fullwidth_punctuation(text) == 1.0

    def test_leading_list_markers_ignored(self) -> None:
        text = "1. 以先验开始当前时期。\n2) 观测当前测量值。\n- 更新先验以得到后验。"
        assert check_fullwidth_punctuation(text) == 1.0

    def test_decimal_point_ignored(self) -> None:
        text = "折现因子为 0.95，这很重要。"
        assert check_fullwidth_punctuation(text) == 1.0

    def test_url_ignored(self) -> None:
        text = "详见 https://quantecon.org/zh-cn/ 获取更多信息。"
        assert check_fullwidth_punctuation(text) == 1.0

    def test_url_does_not_swallow_the_rest_of_a_cjk_line(self) -> None:
        """Chinese prose has no spaces, so a URL must be bounded by CJK too.

        Matching a URL as ``\\S+`` would consume the whole tail of the line
        and hide every punctuation error after a link.
        """
        text = "详见https://example.com,这很重要,真的"
        assert check_fullwidth_punctuation(text) == 0.0

    def test_url_abutting_fullwidth_punctuation_still_scores_clean(self) -> None:
        text = "详见https://example.com/a.b.c，这很重要。"
        assert check_fullwidth_punctuation(text) == 1.0

    def test_markdown_link_not_penalised(self) -> None:
        relative = "请参阅 [讲座](lecture.md) 了解详情。"
        absolute = "请参阅 [讲座](https://example.com/lecture) 了解详情。"
        assert check_fullwidth_punctuation(relative) == 1.0
        assert check_fullwidth_punctuation(absolute) == 1.0

    def test_genuine_ascii_comma_still_fails(self) -> None:
        text = "这是一个测试,包含半角标点"
        assert check_fullwidth_punctuation(text) == 0.0

    def test_genuine_ascii_full_stop_still_fails(self) -> None:
        text = "这是一个测试.包含半角标点"
        assert check_fullwidth_punctuation(text) == 0.0

    def test_mixed_with_structural_ascii(self) -> None:
        """List marker and decimal are stripped; one full-width comma vs one ASCII stop."""
        text = "1. 参数为 0.95，这很重要.结束"
        assert check_fullwidth_punctuation(text) == 0.5

    def test_thousands_separator_ignored_but_prose_comma_is_not(self) -> None:
        clean = "人口为 1,000,000，这很重要。"
        dirty = "人口为 1,000,000,这很重要。"
        assert check_fullwidth_punctuation(clean) == 1.0
        assert check_fullwidth_punctuation(dirty) < 1.0


class TestDirectiveSpacing:
    def test_correct_spacing(self) -> None:
        text = "请参阅 {doc}`介绍 <intro>`"
        assert check_directive_spacing(text) == 1.0

    def test_missing_spacing(self) -> None:
        text = "请参阅{doc}`介绍 <intro>`"
        assert check_directive_spacing(text) == 0.0

    def test_mixed(self) -> None:
        text = "请参阅 {doc}`介绍 <intro>`，还有见{ref}`章节`"
        score = check_directive_spacing(text)
        assert score == 0.5

    def test_no_directives(self) -> None:
        text = "这是普通文本"
        assert check_directive_spacing(text) == 1.0


class TestFormattingScore:
    def test_returns_all_keys(self) -> None:
        result = formatting_score("source text", "translated text")
        assert "directive_balance" in result
        assert "fence_consistency" in result
        assert "code_block_integrity" in result
        assert "fullwidth_punctuation" in result
        assert "directive_spacing" in result

    def test_perfect_score(self) -> None:
        source = "Some text\n```python\nx = 1\n```"
        translated = "一些文本\n```python\nx = 1\n```"
        result = formatting_score(source, translated)
        assert result["directive_balance"] is True
        assert result["code_block_integrity"] is True
