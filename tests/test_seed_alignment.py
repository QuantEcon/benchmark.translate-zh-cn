"""Tests for the seeder's en/zh pair validator.

``_shared_markers`` is what decides whether an extracted pair becomes a
dataset entry. The version that seeded the dataset accepted a pair as soon
as it shared any single marker, which admitted eight misaligned entries
(#31). These tests pin the cases that slipped through.
"""

from __future__ import annotations

from audit_alignment import check_pair
from seed_from_lectures import _shared_markers

# The real para-009 pair: an English table of inter-industry output against
# an unrelated Chinese sentence about it. Both contain $x_1$, which is all
# the old validator required.
TABLE_EN = (
    "|             | Total output | Agriculture | Industry | Service | Consumer |\n"
    "|:-----------:|:------------:|:-----------:|:--------:|:-------:|:--------:|\n"
    "| Agriculture |     $x_1$    |   0.3$x_1$  | 0.2$x_2$ |0.3$x_3$ |     4    |\n"
    "|   Industry  |     $x_2$    |   0.2$x_1$  | 0.4$x_2$ |0.3$x_3$ |     5    |\n"
    "|   Service   |     $x_3$    |   0.2$x_1$  | 0.5$x_2$ |0.1$x_3$ |    12    |"
)
UNRELATED_ZH = "第一行描述了农业的总产出$x_1$是如何分配的"

# The real para-007 pair: four eigenvalue properties against only the first.
LIST_EN = (
    "1. the determinant of $A$ equals the product of the eigenvalues "
    "2. the trace of $A$ (the sum of the elements on the principal diagonal) "
    "equals the sum of the eigenvalues 3. if $A$ is symmetric, then all of its "
    "eigenvalues are real 4. if $A$ is invertible and $\\lambda_1, \\ldots, "
    "\\lambda_n$ are its eigenvalues, then the eigenvalues of $A^{-1}$ are "
    "$1/\\lambda_1, \\ldots, 1/\\lambda_n$."
)
TRUNCATED_ZH = "1. $A$ 的行列式等于其特征值的乘积"


class TestRejectsTheEntriesThatSlippedThrough:
    def test_table_against_unrelated_sentence(self) -> None:
        """One shared math span is not evidence of correspondence."""
        assert _shared_markers(TABLE_EN, UNRELATED_ZH) is False

    def test_truncated_translation(self) -> None:
        assert _shared_markers(LIST_EN, TRUNCATED_ZH) is False

    def test_relettered_exercise(self) -> None:
        """para-014 paired exercise part c) with part d)."""
        en = (
            "**c)** Now pretend that the true value of $\\theta = .4$ and that someone "
            "who doesn't know this has a beta prior distribution with parameters with "
            "$\\beta = \\alpha = .5$. Please write a Python class to simulate this "
            "person's personal posterior distribution for $\\theta$ for a _single_ "
            "sequence of $n$ draws."
        )
        zh = "**d)** 请绘制当 $n$ 增长为 $1, 2, \\ldots$ 时，$\\theta$ 的后验分布关于 $\\theta$ 的函数图。"
        assert _shared_markers(en, zh) is False

    def test_dropped_citations(self) -> None:
        """sent-001 dropped both {cite} refs and the lambda clause."""
        en = (
            "We assume that the expected rate of inflation $\\pi_t^*$ is governed by "
            "the following adaptive expectations scheme proposed by {cite}`Friedman1956` "
            "and {cite}`Cagan`, where $\\lambda\\in [0,1]$ denotes the weight on "
            "expected inflation."
        )
        zh = "我们假设预期通胀率 $\\pi_t^*$ 遵循弗里德曼-凯根的自适应预期机制："
        assert _shared_markers(en, zh) is False


class TestAcceptsGenuinePairs:
    def test_faithful_translation_with_markers(self) -> None:
        en = (
            "Given the dynamics in {eq}`ar1_ma` and initial conditions "
            "$\\mu_0, v_0$, we obtain $\\mu_t, v_t$ and hence"
        )
        zh = "给定 {eq}`ar1_ma` 中的动态和初始条件 $\\mu_0, v_0$，我们得到 $\\mu_t, v_t$，因此"
        assert _shared_markers(en, zh) is True

    def test_repaired_list_is_accepted(self) -> None:
        """The correct counterpart for LIST_EN, which the old code truncated."""
        zh = (
            "1. $A$ 的行列式等于其特征值的乘积\n"
            "2. $A$ 的迹（主对角线上元素的和）等于其特征值的和\n"
            "3. 如果 $A$ 是对称的，那么它的所有特征值都是实数\n"
            "4. 如果 $A$ 可逆，且 $\\lambda_1, \\ldots, \\lambda_n$ 是它的特征值，"
            "那么 $A^{-1}$ 的特征值是 $1/\\lambda_1, \\ldots, 1/\\lambda_n$。"
        )
        assert _shared_markers(LIST_EN, zh) is True

    def test_plain_prose_within_ratio(self) -> None:
        en = "This lecture describes a model of inflation dynamics in some detail."
        zh = "本讲座详细描述了一个通货膨胀动态模型，涵盖其主要特征。"
        assert _shared_markers(en, zh) is True


class TestEdgeCases:
    def test_empty_either_side_is_rejected(self) -> None:
        assert _shared_markers("", "") is False
        assert _shared_markers("some English text", "   ") is False
        assert _shared_markers("   ", "一些中文") is False


class TestSeederAgreesWithAudit:
    def test_anything_seeded_would_pass_the_audit(self) -> None:
        """The two rules must not drift — that split is what caused #31."""
        pairs = [
            (TABLE_EN, UNRELATED_ZH),
            (LIST_EN, TRUNCATED_ZH),
            (
                "Given the dynamics in {eq}`ar1_ma` and initial conditions $\\mu_0$, "
                "we obtain $\\mu_t$",
                "给定 {eq}`ar1_ma` 中的动态和初始条件 $\\mu_0$，我们得到 $\\mu_t$",
            ),
        ]
        for en, zh in pairs:
            if _shared_markers(en, zh):
                assert check_pair(en, zh) == [], f"seeder accepted a pair the audit flags: {en[:40]}"
