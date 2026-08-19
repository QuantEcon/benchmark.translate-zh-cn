"""Tests for the translate command logic (non-interactive parts)."""

from __future__ import annotations

import json
import random
from collections import Counter
from pathlib import Path

import pytest

from qebench.commands.translate import (
    WEIGHT_NEEDS_SECOND,
    WEIGHT_UNSEEN,
    WEIGHT_WELL_COVERED,
    _annotator_coverage,
    _char_overlap,
    _entry_weight,
    _needs_second_annotator,
    _pick_entries,
    _save_attempt,
)
from qebench.models import Difficulty, Term


@pytest.fixture()
def sample_terms():
    return [
        Term(id="term-001", en="inflation", zh="通货膨胀", domain="economics", difficulty=Difficulty.basic),
        Term(id="term-002", en="equilibrium", zh="均衡", domain="economics", difficulty=Difficulty.intermediate),
        Term(id="term-003", en="eigenvalue", zh="特征值", domain="mathematics", difficulty=Difficulty.advanced),
        Term(id="term-004", en="variance", zh="方差", domain="statistics", difficulty=Difficulty.basic),
        Term(
            id="term-005", en="Bellman equation", zh="贝尔曼方程",
            domain="dynamic-programming", difficulty=Difficulty.advanced,
        ),
    ]


@pytest.fixture()
def results_dir(tmp_path, monkeypatch):
    """Point RESULTS_DIR at an empty temp directory of attempt files."""
    directory = tmp_path / "translations"
    directory.mkdir()
    monkeypatch.setattr("qebench.commands.translate.RESULTS_DIR", directory)
    return directory


def _write_attempts(directory: Path, username: str, entry_ids: list[str]) -> None:
    """Write one attempt record per entry id into ``<username>.jsonl``."""
    lines = [
        json.dumps({"entry_id": eid, "attempt": "x", "reference": "y"}, ensure_ascii=False)
        for eid in entry_ids
    ]
    with open(directory / f"{username}.jsonl", "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


class TestAnnotatorCoverage:
    def test_missing_directory_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr("qebench.commands.translate.RESULTS_DIR", tmp_path / "nope")
        assert _annotator_coverage() == {}

    def test_empty_directory_returns_empty(self, results_dir):
        assert _annotator_coverage() == {}

    def test_collects_distinct_usernames_per_entry(self, results_dir):
        _write_attempts(results_dir, "alice", ["term-001", "term-002"])
        _write_attempts(results_dir, "bob", ["term-002"])
        coverage = _annotator_coverage()
        assert coverage == {"term-001": {"alice"}, "term-002": {"alice", "bob"}}

    def test_repeat_attempts_by_same_user_count_once(self, results_dir):
        _write_attempts(results_dir, "alice", ["term-001", "term-001", "term-001"])
        assert _annotator_coverage() == {"term-001": {"alice"}}

    def test_skips_malformed_lines(self, results_dir):
        path = results_dir / "alice.jsonl"
        path.write_text(
            '{"entry_id": "term-001"}\n'
            "{not json at all\n"
            "\n"
            '{"entry_id": "term-002"}\n',
            encoding="utf-8",
        )
        assert _annotator_coverage() == {"term-001": {"alice"}, "term-002": {"alice"}}

    def test_undecodable_file_does_not_lose_other_annotators(self, results_dir):
        """Contributors hand-edit these files; one saved as GBK must not abort the session.

        UnicodeDecodeError comes from the file iterator, not from json.loads,
        so guarding only the parse leaves it uncaught.
        """
        _write_attempts(results_dir, "alice", ["term-001"])
        (results_dir / "bob.jsonl").write_bytes(
            json.dumps({"entry_id": "term-002", "attempt": "通货膨胀"}, ensure_ascii=False).encode("gbk")
            + b"\n"
        )
        assert _annotator_coverage() == {"term-001": {"alice"}}

    def test_unreadable_file_does_not_lose_other_annotators(self, results_dir, monkeypatch):
        """A file that cannot be opened at all is skipped, not fatal."""
        _write_attempts(results_dir, "alice", ["term-001"])
        _write_attempts(results_dir, "bob", ["term-002"])

        real_open = open

        def fail_on_bob(path, *args, **kwargs):
            if str(path).endswith("bob.jsonl"):
                raise OSError("permission denied")
            return real_open(path, *args, **kwargs)

        monkeypatch.setattr("builtins.open", fail_on_bob)
        assert _annotator_coverage() == {"term-001": {"alice"}}

    def test_skips_records_without_usable_entry_id(self, results_dir):
        path = results_dir / "alice.jsonl"
        path.write_text(
            '{"attempt": "no id here"}\n'
            '{"entry_id": ""}\n'
            '{"entry_id": 42}\n'
            "[1, 2, 3]\n"
            '{"entry_id": "term-009"}\n',
            encoding="utf-8",
        )
        assert _annotator_coverage() == {"term-009": {"alice"}}

    def test_username_comes_from_file_stem(self, results_dir):
        _write_attempts(results_dir, "0x3f-Li", ["term-001"])
        assert _annotator_coverage() == {"term-001": {"0x3f-Li"}}


class TestEntryWeight:
    def test_one_other_annotator_is_heaviest(self):
        coverage = {"a": {"alice"}, "b": set(), "c": {"alice", "bob"}}
        weights = {eid: _entry_weight(eid, coverage, "carol") for eid in "abc"}
        assert weights["a"] > weights["b"] > weights["c"]

    def test_own_attempts_do_not_count_towards_consensus(self):
        """Another user's single attempt makes an entry valuable; your own does not."""
        coverage = {"mine": {"carol"}, "theirs": {"alice"}}
        assert _entry_weight("theirs", coverage, "carol") == WEIGHT_NEEDS_SECOND
        assert _entry_weight("mine", coverage, "carol") == WEIGHT_WELL_COVERED

    def test_entry_the_user_already_annotated_is_never_prioritised(self):
        """Reachable via the empty-pool fallback, where own entries are not filtered out.

        ``{carol, alice}`` leaves exactly one *other* annotator, which would
        otherwise read as "needs a second" — but carol is already that second.
        """
        coverage = {"a": {"carol", "alice"}}
        assert _entry_weight("a", coverage, "carol") == WEIGHT_WELL_COVERED

    def test_unknown_entry_treated_as_unseen(self):
        assert _entry_weight("missing", {}, "carol") == WEIGHT_UNSEEN

    def test_weight_constants_are_ordered(self):
        assert WEIGHT_NEEDS_SECOND > WEIGHT_UNSEEN > WEIGHT_WELL_COVERED > 0

    def test_needs_second_annotator_flag(self):
        coverage = {"a": {"alice"}, "b": {"alice", "bob"}, "c": {"carol"}}
        assert _needs_second_annotator("a", coverage, "carol")
        assert not _needs_second_annotator("b", coverage, "carol")
        assert not _needs_second_annotator("c", coverage, "carol")
        assert not _needs_second_annotator("d", coverage, "carol")

    def test_entry_the_user_already_annotated_does_not_need_a_second(self):
        """carol + one other is already two annotators — carol cannot be the 2nd."""
        coverage = {"a": {"carol", "alice"}}
        assert not _needs_second_annotator("a", coverage, "carol")


class TestPickEntries:
    def test_returns_requested_count(self, sample_terms):
        result = _pick_entries(sample_terms, [], [], None, None, 3, coverage={})
        assert len(result) == 3

    def test_returns_all_if_count_exceeds_pool(self, sample_terms):
        result = _pick_entries(sample_terms, [], [], None, None, 100, coverage={})
        assert len(result) == 5

    def test_filter_by_domain(self, sample_terms):
        result = _pick_entries(sample_terms, [], [], "economics", None, 10, coverage={})
        assert all(e.domain == "economics" for e in result)
        assert len(result) == 2

    def test_filter_by_difficulty(self, sample_terms):
        result = _pick_entries(sample_terms, [], [], None, "basic", 10, coverage={})
        assert all(e.difficulty == Difficulty.basic for e in result)
        assert len(result) == 2

    def test_filter_by_both(self, sample_terms):
        result = _pick_entries(sample_terms, [], [], "economics", "basic", 10, coverage={})
        assert len(result) == 1
        assert result[0].id == "term-001"

    def test_returns_empty_for_no_match(self, sample_terms):
        result = _pick_entries(sample_terms, [], [], "nonexistent", None, 10, coverage={})
        assert result == []

    def test_filters_still_apply_with_coverage_weighting(self, sample_terms):
        coverage = {"term-001": {"alice"}, "term-003": {"alice", "bob"}}
        result = _pick_entries(
            sample_terms, [], [], None, "advanced", 10,
            username="carol", coverage=coverage,
        )
        assert {e.id for e in result} == {"term-003", "term-005"}

    def test_randomizes_order(self, sample_terms):
        """Multiple calls should eventually produce different orderings."""
        orders = set()
        for _ in range(20):
            result = _pick_entries(sample_terms, [], [], None, None, 5, coverage={})
            orders.add(tuple(e.id for e in result))
        assert len(orders) > 1  # at least two different orderings

    def test_never_returns_an_entry_twice(self, sample_terms):
        coverage = {"term-001": {"alice"}, "term-002": {"alice"}}
        random.seed(7)
        for count in (1, 3, 5, 50):
            result = _pick_entries(
                sample_terms, [], [], None, None, count,
                username="carol", coverage=coverage,
            )
            ids = [e.id for e in result]
            assert len(ids) == len(set(ids))
            assert len(ids) == min(count, len(sample_terms))

    def test_reads_coverage_from_disk_when_not_supplied(self, sample_terms, results_dir):
        _write_attempts(results_dir, "carol", ["term-001", "term-002", "term-003"])
        result = _pick_entries(sample_terms, [], [], None, None, 10, username="carol")
        assert {e.id for e in result} == {"term-004", "term-005"}


class TestConsensusWeighting:
    def test_prefers_entry_needing_a_second_annotator(self, sample_terms):
        """A one-annotator entry beats unseen and well-covered ones over many trials."""
        coverage = {
            "term-001": {"alice"},                  # needs a second annotator
            "term-003": {"alice", "bob", "dave"},   # already well covered
            "term-004": {"alice", "bob"},           # already well covered
            "term-005": {"alice", "bob"},           # already well covered
        }
        # term-002 is unseen.
        random.seed(1234)
        picks = Counter()
        for _ in range(400):
            result = _pick_entries(
                sample_terms, [], [], None, None, 1,
                username="carol", coverage=coverage,
            )
            picks[result[0].id] += 1

        assert picks["term-001"] > picks["term-002"]  # needs-second beats unseen
        assert picks["term-002"] > picks["term-003"]  # unseen beats well-covered
        assert picks["term-001"] > 400 * 0.4

    def test_excludes_entries_the_current_user_already_attempted(self, sample_terms):
        coverage = {
            "term-001": {"carol"},
            "term-002": {"carol", "alice"},
            "term-003": {"alice"},
        }
        random.seed(99)
        for _ in range(30):
            result = _pick_entries(
                sample_terms, [], [], None, None, 5,
                username="carol", coverage=coverage,
            )
            ids = {e.id for e in result}
            assert "term-001" not in ids
            assert "term-002" not in ids
            assert ids == {"term-003", "term-004", "term-005"}

    def test_other_users_attempts_are_not_excluded(self, sample_terms):
        coverage = {e.id: {"alice"} for e in sample_terms}
        result = _pick_entries(
            sample_terms, [], [], None, None, 5,
            username="carol", coverage=coverage,
        )
        assert len(result) == 5

    def test_falls_back_to_full_pool_when_user_covered_everything(self, sample_terms):
        coverage = {e.id: {"carol"} for e in sample_terms}
        result = _pick_entries(
            sample_terms, [], [], None, None, 3,
            username="carol", coverage=coverage,
        )
        assert len(result) == 3

    def test_fallback_respects_filters(self, sample_terms):
        coverage = {e.id: {"carol"} for e in sample_terms}
        result = _pick_entries(
            sample_terms, [], [], "economics", None, 10,
            username="carol", coverage=coverage,
        )
        assert {e.id for e in result} == {"term-001", "term-002"}


class TestUniformMode:
    def test_uniform_ignores_coverage_weighting(self, sample_terms):
        """--uniform gives every entry a comparable share of single-entry draws."""
        coverage = {
            "term-001": {"alice"},
            "term-003": {"alice", "bob", "dave"},
            "term-004": {"alice", "bob"},
            "term-005": {"alice", "bob"},
        }
        random.seed(2024)
        picks = Counter()
        for _ in range(500):
            result = _pick_entries(
                sample_terms, [], [], None, None, 1,
                username="carol", coverage=coverage, uniform=True,
            )
            picks[result[0].id] += 1

        assert len(picks) == len(sample_terms)
        expected = 500 / len(sample_terms)
        assert all(0.6 * expected < n < 1.4 * expected for n in picks.values())

    def test_uniform_keeps_entries_the_user_already_attempted(self, sample_terms):
        coverage = {e.id: {"carol"} for e in sample_terms}
        result = _pick_entries(
            sample_terms, [], [], None, None, 5,
            username="carol", coverage=coverage, uniform=True,
        )
        assert {e.id for e in result} == {e.id for e in sample_terms}

    def test_uniform_does_not_read_results_from_disk(self, sample_terms, monkeypatch):
        def _boom() -> dict[str, set[str]]:
            raise AssertionError("coverage should not be loaded in uniform mode")

        monkeypatch.setattr("qebench.commands.translate._annotator_coverage", _boom)
        result = _pick_entries(sample_terms, [], [], None, None, 2, username="carol", uniform=True)
        assert len(result) == 2

    def test_uniform_still_applies_filters(self, sample_terms):
        result = _pick_entries(
            sample_terms, [], [], "economics", "basic", 10,
            username="carol", uniform=True,
        )
        assert len(result) == 1
        assert result[0].id == "term-001"


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


class TestCharOverlap:
    def test_identical_strings(self):
        assert _char_overlap("贝尔曼方程", "贝尔曼方程") == 1.0

    def test_completely_different(self):
        assert _char_overlap("你好", "世界") == 0.0

    def test_partial_overlap(self):
        overlap = _char_overlap("通货膨胀率", "通货膨胀")
        assert 0.5 < overlap < 1.0

    def test_empty_strings(self):
        assert _char_overlap("", "") == 1.0

    def test_one_empty(self):
        assert _char_overlap("", "你好") == 0.0
        assert _char_overlap("你好", "") == 0.0

    def test_ignores_punctuation(self):
        assert _char_overlap("你好，世界！", "你好世界") == 1.0

    def test_symmetry(self):
        a = _char_overlap("经济学", "经济")
        b = _char_overlap("经济", "经济学")
        assert a == b


class TestSaveAttempt:
    def test_saves_record_with_confidence_and_similarity(self, tmp_path, monkeypatch):
        monkeypatch.setattr("qebench.commands.translate.RESULTS_DIR", tmp_path)
        _save_attempt("term-001", "通货膨胀", "通货膨胀", 4, 1.0, "", "", "alice")
        filepath = tmp_path / "alice.jsonl"
        assert filepath.exists()
        record = json.loads(filepath.read_text(encoding="utf-8").strip())
        assert record["entry_id"] == "term-001"
        assert record["confidence"] == 4
        assert record["similarity"] == 1.0
        assert "diff_reason" not in record  # omitted when empty
        assert "notes" not in record  # omitted when empty
        assert "timestamp" in record
        assert "cli_version" in record

    def test_saves_diff_reason(self, tmp_path, monkeypatch):
        monkeypatch.setattr("qebench.commands.translate.RESULTS_DIR", tmp_path)
        _save_attempt("term-002", "通胀", "通货膨胀", 3, 0.5, "abbreviation", "shorter form", "alice")
        filepath = tmp_path / "alice.jsonl"
        record = json.loads(filepath.read_text(encoding="utf-8").strip())
        assert record["diff_reason"] == "abbreviation"
        assert record["notes"] == "shorter form"
        assert record["similarity"] == 0.5

    def test_appends_multiple_records(self, tmp_path, monkeypatch):
        monkeypatch.setattr("qebench.commands.translate.RESULTS_DIR", tmp_path)
        _save_attempt("term-001", "A", "B", 2, 0.0, "", "", "bob")
        _save_attempt("term-002", "C", "D", 5, 1.0, "", "", "bob")
        filepath = tmp_path / "bob.jsonl"
        lines = [
            ln for ln in filepath.read_text(encoding="utf-8").splitlines() if ln.strip()
        ]
        assert len(lines) == 2

    def test_omits_empty_optional_fields(self, tmp_path, monkeypatch):
        """diff_reason and notes are omitted from JSON when empty."""
        monkeypatch.setattr("qebench.commands.translate.RESULTS_DIR", tmp_path)
        _save_attempt("term-001", "X", "Y", 3, 0.8, "", "", "carol")
        filepath = tmp_path / "carol.jsonl"
        record = json.loads(filepath.read_text(encoding="utf-8").strip())
        assert "diff_reason" not in record
        assert "notes" not in record
        assert "similarity" in record


class TestSaveAttemptFeedsCoverage:
    def test_saved_attempt_appears_in_coverage(self, results_dir):
        _save_attempt("term-001", "通货膨胀", "通货膨胀", 4, 1.0, "", "", "alice")
        _save_attempt("term-001", "通胀", "通货膨胀", 3, 0.5, "abbreviation", "", "bob")
        assert _annotator_coverage() == {"term-001": {"alice", "bob"}}
