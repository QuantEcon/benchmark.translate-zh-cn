"""Tests for the stats command."""

from __future__ import annotations

import json

from qebench.commands.stats import _load_leaderboard


class TestLoadLeaderboard:
    def test_empty_directory(self, tmp_path, monkeypatch):
        monkeypatch.setattr("qebench.commands.stats.XP_DIR", tmp_path)
        assert _load_leaderboard() == []

    def test_no_directory(self, tmp_path, monkeypatch):
        monkeypatch.setattr("qebench.commands.stats.XP_DIR", tmp_path / "nonexistent")
        assert _load_leaderboard() == []

    def test_single_user(self, tmp_path, monkeypatch):
        monkeypatch.setattr("qebench.commands.stats.XP_DIR", tmp_path)
        (tmp_path / "alice.json").write_text(
            json.dumps({"total": 50, "actions": {"translate": 30, "add": 20}}),
            encoding="utf-8",
        )
        result = _load_leaderboard()
        assert len(result) == 1
        assert result[0]["username"] == "alice"
        assert result[0]["total"] == 50

    def test_sorted_by_total_desc(self, tmp_path, monkeypatch):
        monkeypatch.setattr("qebench.commands.stats.XP_DIR", tmp_path)
        (tmp_path / "alice.json").write_text(
            json.dumps({"total": 30, "actions": {"translate": 30}}),
            encoding="utf-8",
        )
        (tmp_path / "bob.json").write_text(
            json.dumps({"total": 100, "actions": {"translate": 60, "add": 40}}),
            encoding="utf-8",
        )
        result = _load_leaderboard()
        assert len(result) == 2
        assert result[0]["username"] == "bob"
        assert result[1]["username"] == "alice"
