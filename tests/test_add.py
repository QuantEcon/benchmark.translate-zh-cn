"""Tests for the add command."""

from __future__ import annotations

import json

from qebench.commands.add import _find_duplicates, _save_to_user_file
from qebench.models import Difficulty, Sentence, Term


class TestFindDuplicates:
    def _make_terms(self):
        return [
            Term(
                id="term-001", en="inflation", zh="通货膨胀",
                domain="economics", difficulty=Difficulty.basic,
            ),
            Term(
                id="term-002", en="Gross Domestic Product", zh="国内生产总值",
                domain="economics", difficulty=Difficulty.basic,
            ),
        ]

    def test_exact_match(self):
        terms = self._make_terms()
        dupes = _find_duplicates("inflation", terms)
        assert len(dupes) == 1
        assert dupes[0].id == "term-001"

    def test_case_insensitive(self):
        terms = self._make_terms()
        dupes = _find_duplicates("INFLATION", terms)
        assert len(dupes) == 1
        assert dupes[0].id == "term-001"

    def test_whitespace_normalised(self):
        terms = self._make_terms()
        dupes = _find_duplicates("  inflation  ", terms)
        assert len(dupes) == 1

    def test_no_match(self):
        terms = self._make_terms()
        dupes = _find_duplicates("deflation", terms)
        assert dupes == []

    def test_works_with_sentences(self):
        sentences = [
            Sentence(
                id="sent-001", en="The rate of inflation is rising.",
                zh="通胀率正在上升。", domain="economics", difficulty=Difficulty.basic,
            ),
        ]
        dupes = _find_duplicates("the rate of inflation is rising.", sentences)
        assert len(dupes) == 1


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
