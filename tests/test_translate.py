"""Tests for the translate command logic (non-interactive parts)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qebench.commands.translate import _pick_entries, _save_attempt
from qebench.models import Difficulty, Term


@pytest.fixture()
def sample_terms():
    return [
        Term(id="term-001", en="inflation", zh="通货膨胀", domain="economics", difficulty=Difficulty.basic),
        Term(id="term-002", en="equilibrium", zh="均衡", domain="economics", difficulty=Difficulty.intermediate),
        Term(id="term-003", en="eigenvalue", zh="特征值", domain="mathematics", difficulty=Difficulty.advanced),
        Term(id="term-004", en="variance", zh="方差", domain="statistics", difficulty=Difficulty.basic),
        Term(id="term-005", en="Bellman equation", zh="贝尔曼方程", domain="dynamic-programming", difficulty=Difficulty.advanced),
    ]


class TestPickEntries:
    def test_returns_requested_count(self, sample_terms):
        result = _pick_entries(sample_terms, [], [], None, None, 3)
        assert len(result) == 3

    def test_returns_all_if_count_exceeds_pool(self, sample_terms):
        result = _pick_entries(sample_terms, [], [], None, None, 100)
        assert len(result) == 5

    def test_filter_by_domain(self, sample_terms):
        result = _pick_entries(sample_terms, [], [], "economics", None, 10)
        assert all(e.domain == "economics" for e in result)
        assert len(result) == 2

    def test_filter_by_difficulty(self, sample_terms):
        result = _pick_entries(sample_terms, [], [], None, "basic", 10)
        assert all(e.difficulty == Difficulty.basic for e in result)
        assert len(result) == 2

    def test_filter_by_both(self, sample_terms):
        result = _pick_entries(sample_terms, [], [], "economics", "basic", 10)
        assert len(result) == 1
        assert result[0].id == "term-001"

    def test_returns_empty_for_no_match(self, sample_terms):
        result = _pick_entries(sample_terms, [], [], "nonexistent", None, 10)
        assert result == []

    def test_randomizes_order(self, sample_terms):
        """Multiple calls should eventually produce different orderings."""
        orders = set()
        for _ in range(20):
            result = _pick_entries(sample_terms, [], [], None, None, 5)
            orders.add(tuple(e.id for e in result))
        assert len(orders) > 1  # at least two different orderings


class TestAddNextId:
    def test_generates_sequential_ids(self):
        from qebench.commands.add import _next_id

        terms = [
            Term(id="term-001", en="a", zh="b", domain="x", difficulty=Difficulty.basic),
            Term(id="term-002", en="c", zh="d", domain="x", difficulty=Difficulty.basic),
        ]
        assert _next_id("term", terms) == "term-003"

    def test_handles_empty_list(self):
        from qebench.commands.add import _next_id

        assert _next_id("term", []) == "term-001"

    def test_handles_gaps(self):
        from qebench.commands.add import _next_id

        terms = [
            Term(id="term-001", en="a", zh="b", domain="x", difficulty=Difficulty.basic),
            Term(id="term-010", en="c", zh="d", domain="x", difficulty=Difficulty.basic),
        ]
        assert _next_id("term", terms) == "term-011"


class TestSaveAttempt:
    def test_saves_record_with_confidence(self, tmp_path, monkeypatch):
        monkeypatch.setattr("qebench.commands.translate.RESULTS_DIR", tmp_path)
        _save_attempt("term-001", "通货膨胀", "通货膨胀", 4, "", "alice")
        filepath = tmp_path / "alice.jsonl"
        assert filepath.exists()
        record = json.loads(filepath.read_text(encoding="utf-8").strip())
        assert record["entry_id"] == "term-001"
        assert record["confidence"] == 4
        assert record["notes"] == ""
        assert "timestamp" in record

    def test_saves_notes(self, tmp_path, monkeypatch):
        monkeypatch.setattr("qebench.commands.translate.RESULTS_DIR", tmp_path)
        _save_attempt("term-002", "均衡", "均衡", 3, "common econ term", "alice")
        filepath = tmp_path / "alice.jsonl"
        record = json.loads(filepath.read_text(encoding="utf-8").strip())
        assert record["notes"] == "common econ term"

    def test_appends_multiple_records(self, tmp_path, monkeypatch):
        monkeypatch.setattr("qebench.commands.translate.RESULTS_DIR", tmp_path)
        _save_attempt("term-001", "A", "B", 2, "", "bob")
        _save_attempt("term-002", "C", "D", 5, "sure", "bob")
        filepath = tmp_path / "bob.jsonl"
        lines = [l for l in filepath.read_text(encoding="utf-8").splitlines() if l.strip()]
        assert len(lines) == 2

    def test_no_overlap_field(self, tmp_path, monkeypatch):
        """Overlap scoring was removed — records should not contain it."""
        monkeypatch.setattr("qebench.commands.translate.RESULTS_DIR", tmp_path)
        _save_attempt("term-001", "X", "Y", 3, "", "carol")
        filepath = tmp_path / "carol.jsonl"
        record = json.loads(filepath.read_text(encoding="utf-8").strip())
        assert "overlap" not in record
