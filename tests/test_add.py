"""Tests for the add command."""

from __future__ import annotations

import json

from qebench.commands.add import _save_to_user_file
from qebench.models import Difficulty, Term


class TestSaveToUserFile:
    def test_stamps_cli_version(self, tmp_path, monkeypatch):
        monkeypatch.setattr("qebench.commands.add.DATA_DIR", tmp_path)
        term = Term(
            id="term-001", en="inflation", zh="通货膨胀",
            domain="economics", difficulty=Difficulty.basic,
        )
        filepath = _save_to_user_file(term, "terms", "alice")
        with open(filepath, encoding="utf-8") as f:
            entries = json.load(f)
        assert len(entries) == 1
        assert entries[0]["cli_version"] == __import__("qebench").__version__

    def test_appends_to_existing(self, tmp_path, monkeypatch):
        monkeypatch.setattr("qebench.commands.add.DATA_DIR", tmp_path)
        t1 = Term(id="term-001", en="a", zh="b", domain="x", difficulty=Difficulty.basic)
        t2 = Term(id="term-002", en="c", zh="d", domain="x", difficulty=Difficulty.basic)
        _save_to_user_file(t1, "terms", "alice")
        _save_to_user_file(t2, "terms", "alice")
        filepath = tmp_path / "terms" / "alice.json"
        with open(filepath, encoding="utf-8") as f:
            entries = json.load(f)
        assert len(entries) == 2
        assert all("cli_version" in e for e in entries)
