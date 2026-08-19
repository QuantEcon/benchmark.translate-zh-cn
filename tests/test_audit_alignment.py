"""Tests for the en/zh alignment audit script."""

from __future__ import annotations

import json
from pathlib import Path

from audit_alignment import audit, audit_file, check_pair, math_spans, role_targets

# A faithful zh translation of the en source below: same math, same reference
# target, plausible length.
GOOD_EN = "Given the dynamics in {eq}`ar1_ma` and initial conditions $\\mu_0$, we obtain $\\mu_t$."
GOOD_ZH = "给定 {eq}`ar1_ma` 中的动态和初始条件 $\\mu_0$，我们得到 $\\mu_t$。"


class TestMathSpans:
    def test_extracts_inline_math(self) -> None:
        assert math_spans("value $x_1$ and $y_2$") == {"$x_1$", "$y_2$"}

    def test_no_math(self) -> None:
        assert math_spans("plain prose") == set()

    def test_does_not_span_newlines(self) -> None:
        assert math_spans("$a\nb$") == set()


class TestRoleTargets:
    def test_bare_role_uses_body_as_target(self) -> None:
        assert role_targets("see {eq}`ar1_ma`") == {("eq", "ar1_ma")}

    def test_display_text_is_excluded(self) -> None:
        """Display text is translated; only the <target> must survive."""
        en = "recall {doc}`our earlier discussion <lln_clt>`"
        zh = "回顾{doc}`之前的讨论 <lln_clt>`"
        assert role_targets(en) == role_targets(zh) == {("doc", "lln_clt")}

    def test_multiple_roles(self) -> None:
        text = "{eq}`a` and {ref}`b`"
        assert role_targets(text) == {("eq", "a"), ("ref", "b")}


class TestCheckPair:
    def test_aligned_pair_has_no_problems(self) -> None:
        assert check_pair(GOOD_EN, GOOD_ZH) == []

    def test_truncated_reference_flagged_on_length(self) -> None:
        problems = check_pair("a" * 400, "短")
        assert any("length ratio" in p for p in problems)

    def test_missing_math_flagged(self) -> None:
        en = "we have $x_1$, $x_2$, $x_3$ and $x_4$ in this reasonably long sentence"
        zh = "我们在这个相当长的句子中有 $x_1$ 这个符号以及其他一些相关的内容说明"
        assert any("math spans missing" in p for p in check_pair(en, zh))

    def test_missing_reference_target_flagged(self) -> None:
        en = "as shown in {eq}`eq:Xfour1a` and {eq}`eq:Xfour1b`, the result follows"
        zh = "如 {eq}`eq:Xfour1b` 所示，结果随之得出，这里补充一些说明文字"
        problems = check_pair(en, zh)
        assert any("eq:Xfour1a" in p for p in problems)

    def test_translated_display_text_is_not_flagged(self) -> None:
        """The check must not punish a correctly translated link label."""
        en = "recall {doc}`our earlier discussion <lln_clt>` of the law of large numbers here"
        zh = "让我们回顾{doc}`之前关于大数定律的讨论 <lln_clt>`，这是一个重要的结果说明"
        assert check_pair(en, zh) == []

    def test_empty_source_does_not_crash(self) -> None:
        assert isinstance(check_pair("", ""), list)

    def test_half_the_math_missing_is_tolerated(self) -> None:
        """Only a majority of missing math spans indicates misalignment."""
        en = "the pair $x_1$ and $x_2$ appear together in this sentence of ordinary length"
        zh = "符号 $x_1$ 出现在这个长度普通的句子中，与另一个符号一起构成完整的表达式"
        assert not any("math spans missing" in p for p in check_pair(en, zh))


class TestAuditFile:
    def test_flags_only_bad_entries(self, tmp_path: Path) -> None:
        path = tmp_path / "seed.json"
        entries = [
            {"id": "sent-001", "en": GOOD_EN, "zh": GOOD_ZH, "source": "a.md"},
            {"id": "sent-002", "en": "a" * 400, "zh": "短", "source": "b.md"},
        ]
        path.write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")

        flagged = audit_file(path)
        assert [r["id"] for r in flagged] == ["sent-002"]
        assert flagged[0]["source"] == "b.md"

    def test_accepts_wrapper_format(self, tmp_path: Path) -> None:
        """Seed files may be a bare list or a {version, entries} wrapper."""
        path = tmp_path / "seed.json"
        payload = {"version": 1, "entries": [{"id": "x", "en": "a" * 400, "zh": "短"}]}
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        assert [r["id"] for r in audit_file(path)] == ["x"]

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        assert audit_file(tmp_path / "nope.json") == []


class TestAudit:
    def test_walks_both_entry_types(self, tmp_path: Path) -> None:
        for kind in ("sentences", "paragraphs"):
            (tmp_path / kind).mkdir()
            entries = [{"id": f"{kind}-bad", "en": "a" * 400, "zh": "短"}]
            (tmp_path / kind / "seed.json").write_text(
                json.dumps(entries, ensure_ascii=False), encoding="utf-8"
            )

        results = audit(tmp_path)
        assert set(results) == {"sentences", "paragraphs"}
        assert [r["id"] for r in results["sentences"]] == ["sentences-bad"]
        assert [r["id"] for r in results["paragraphs"]] == ["paragraphs-bad"]

    def test_empty_dataset_returns_empty_lists(self, tmp_path: Path) -> None:
        for kind in ("sentences", "paragraphs"):
            (tmp_path / kind).mkdir()
        assert audit(tmp_path) == {"sentences": [], "paragraphs": []}
