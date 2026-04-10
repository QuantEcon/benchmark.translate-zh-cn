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
