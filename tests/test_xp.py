"""Tests for XP scoring module."""

from __future__ import annotations

import json

import pytest

from qebench.scoring.xp import (
    XP_ADD,
    XP_JUDGE,
    XP_TRANSLATE,
    award_xp,
    load_xp,
    load_xp_details,
)


@pytest.fixture()
def xp_dir(tmp_path, monkeypatch):
    """Override XP_DIR to use a temp directory."""
    import qebench.scoring.xp as xp_mod

    monkeypatch.setattr(xp_mod, "XP_DIR", tmp_path)
    return tmp_path


class TestXPValues:
    def test_translate_xp_is_10(self):
        assert XP_TRANSLATE == 10

    def test_add_xp_is_15(self):
        assert XP_ADD == 15

    def test_judge_xp_is_5(self):
        assert XP_JUDGE == 5


class TestLoadXP:
    def test_returns_zero_for_new_user(self, xp_dir):
        assert load_xp("newuser") == 0

    def test_returns_total_from_file(self, xp_dir):
        path = xp_dir / "alice.json"
        path.write_text(json.dumps({"total": 150, "actions": {"translate": 100, "add": 50}}))
        assert load_xp("alice") == 150


class TestAwardXP:
    def test_awards_translate_xp(self, xp_dir):
        earned = award_xp("bob", "translate", 3)
        assert earned == 30  # 10 * 3
        assert load_xp("bob") == 30

    def test_awards_add_xp(self, xp_dir):
        earned = award_xp("bob", "add", 2)
        assert earned == 30  # 15 * 2

    def test_awards_judge_xp(self, xp_dir):
        earned = award_xp("bob", "judge", 4)
        assert earned == 20  # 5 * 4

    def test_accumulates_across_calls(self, xp_dir):
        award_xp("carol", "translate", 5)
        award_xp("carol", "add", 1)
        assert load_xp("carol") == 65  # 50 + 15

    def test_unknown_action_awards_zero(self, xp_dir):
        earned = award_xp("dave", "unknown", 10)
        assert earned == 0
        assert load_xp("dave") == 0

    def test_creates_directory_if_missing(self, xp_dir, tmp_path):
        import qebench.scoring.xp as xp_mod

        nested = tmp_path / "deep" / "nested"
        xp_mod.XP_DIR = nested
        award_xp("eve", "translate", 1)
        assert (nested / "eve.json").exists()


class TestLoadXPDetails:
    def test_returns_empty_for_new_user(self, xp_dir):
        details = load_xp_details("nobody")
        assert details == {"total": 0, "actions": {}}

    def test_returns_breakdown(self, xp_dir):
        award_xp("frank", "translate", 2)
        award_xp("frank", "judge", 3)
        details = load_xp_details("frank")
        assert details["total"] == 35  # 20 + 15
        assert details["actions"]["translate"] == 20
        assert details["actions"]["judge"] == 15
