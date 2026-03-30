"""Tests for scoring modules."""

from __future__ import annotations

import pytest

from qebench.scoring.elo import expected_score, update_elo


class TestElo:
    def test_expected_score_equal_ratings(self) -> None:
        assert expected_score(1500, 1500) == pytest.approx(0.5)

    def test_expected_score_higher_rating(self) -> None:
        score = expected_score(1600, 1400)
        assert score > 0.5

    def test_expected_score_lower_rating(self) -> None:
        score = expected_score(1400, 1600)
        assert score < 0.5

    def test_update_elo_winner(self) -> None:
        new_a, new_b = update_elo(1500, 1500, winner="a")
        assert new_a > 1500
        assert new_b < 1500

    def test_update_elo_tie(self) -> None:
        new_a, new_b = update_elo(1500, 1500, winner="tie")
        assert new_a == 1500
        assert new_b == 1500

    def test_update_elo_symmetry(self) -> None:
        new_a1, new_b1 = update_elo(1500, 1500, winner="a")
        new_a2, new_b2 = update_elo(1500, 1500, winner="b")
        assert new_a1 == new_b2
        assert new_b1 == new_a2
