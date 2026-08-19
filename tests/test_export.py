"""Tests for the export command."""

from __future__ import annotations

import builtins
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from qebench.commands.export import (
    _activity_feed,
    _difficulty_stats,
    _domain_stats,
    _term_samples,
    _xp_leaderboard,
    export,
)
from qebench.models import Difficulty, Sentence, Term


def _make_term(id: str, domain: str, difficulty: str = "basic") -> Term:
    return Term(
        id=id,
        en=f"term {id}",
        zh=f"术语{id}",
        domain=domain,
        difficulty=Difficulty(difficulty),
    )


def _make_sentence(id: str, domain: str, difficulty: str = "intermediate") -> Sentence:
    return Sentence(
        id=id,
        en=f"sentence {id}",
        zh=f"句子{id}",
        domain=domain,
        difficulty=Difficulty(difficulty),
    )


def _write_gbk(path: Path, payload: object) -> None:
    """Write a JSON payload encoded as GBK — the realistic way a contributor
    on a Chinese Windows box saves a results file that UTF-8 cannot decode."""
    text = json.dumps(payload, ensure_ascii=False)
    path.write_bytes(text.encode("gbk"))


def _break_open_for(monkeypatch: pytest.MonkeyPatch, filename: str) -> None:
    """Make open() raise OSError for one filename, as an unreadable file would."""
    real_open = builtins.open

    def fake_open(file, *args, **kwargs):  # type: ignore[no-untyped-def]
        if isinstance(file, (str, Path)) and Path(file).name == filename:
            raise OSError(13, "Permission denied")
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", fake_open)


class TestDomainStats:
    def test_empty_lists(self) -> None:
        result = _domain_stats([], [], [])
        assert result == []

    def test_terms_only(self) -> None:
        terms = [
            _make_term("term-001", "economics"),
            _make_term("term-002", "economics"),
            _make_term("term-003", "finance"),
        ]
        result = _domain_stats(terms, [], [])
        assert len(result) == 2
        # Sorted by total descending
        assert result[0]["domain"] == "economics"
        assert result[0]["terms"] == 2
        assert result[1]["domain"] == "finance"
        assert result[1]["terms"] == 1

    def test_mixed_entry_types(self) -> None:
        terms = [_make_term("term-001", "economics")]
        sentences = [_make_sentence("sent-001", "economics")]
        result = _domain_stats(terms, sentences, [])
        assert len(result) == 1
        assert result[0]["terms"] == 1
        assert result[0]["sentences"] == 1
        assert result[0]["paragraphs"] == 0


class TestDifficultyStats:
    def test_empty(self) -> None:
        result = _difficulty_stats([], [], [])
        assert result == {"basic": 0, "intermediate": 0, "advanced": 0}

    def test_counts_across_types(self) -> None:
        terms = [
            _make_term("term-001", "econ", "basic"),
            _make_term("term-002", "econ", "advanced"),
        ]
        sentences = [_make_sentence("sent-001", "econ", "intermediate")]
        result = _difficulty_stats(terms, sentences, [])
        assert result["basic"] == 1
        assert result["intermediate"] == 1
        assert result["advanced"] == 1


class TestXpLeaderboard:
    def test_empty_no_dir(self, tmp_path: Path) -> None:
        with patch("qebench.commands.export._REPO_ROOT", tmp_path):
            result = _xp_leaderboard()
        assert result == []

    def test_loads_and_sorts(self, tmp_path: Path) -> None:
        xp_dir = tmp_path / "results" / "xp"
        xp_dir.mkdir(parents=True)
        (xp_dir / "alice.json").write_text(
            json.dumps({"total": 50, "actions": {"translate": 5}})
        )
        (xp_dir / "bob.json").write_text(
            json.dumps({"total": 120, "actions": {"translate": 8, "add": 3}})
        )
        with patch("qebench.commands.export._REPO_ROOT", tmp_path):
            result = _xp_leaderboard()
        assert len(result) == 2
        assert result[0]["username"] == "bob"
        assert result[0]["total_xp"] == 120
        assert result[1]["username"] == "alice"

    def test_skips_malformed_file(self, tmp_path: Path) -> None:
        xp_dir = tmp_path / "results" / "xp"
        xp_dir.mkdir(parents=True)
        (xp_dir / "good.json").write_text(json.dumps({"total": 30, "actions": {}}))
        (xp_dir / "broken.json").write_text("<<<<<<< Updated upstream")
        with patch("qebench.commands.export._REPO_ROOT", tmp_path):
            result = _xp_leaderboard()
        assert len(result) == 1
        assert result[0]["username"] == "good"

    def test_skips_non_object_file(self, tmp_path: Path) -> None:
        xp_dir = tmp_path / "results" / "xp"
        xp_dir.mkdir(parents=True)
        (xp_dir / "good.json").write_text(json.dumps({"total": 30, "actions": {}}))
        # Valid JSON, but a list rather than an object — must not crash on data.get(...)
        (xp_dir / "list.json").write_text(json.dumps([1, 2, 3]))
        with patch("qebench.commands.export._REPO_ROOT", tmp_path):
            result = _xp_leaderboard()
        assert len(result) == 1
        assert result[0]["username"] == "good"

    def test_skips_misencoded_file(self, tmp_path: Path) -> None:
        # A GBK-encoded file raises UnicodeDecodeError from json.load — that is a
        # ValueError, not a JSONDecodeError or OSError, so it escaped the old guard.
        xp_dir = tmp_path / "results" / "xp"
        xp_dir.mkdir(parents=True)
        (xp_dir / "good.json").write_text(json.dumps({"total": 30, "actions": {}}))
        _write_gbk(xp_dir / "gbk.json", {"total": 99, "actions": {"翻译": 5}})
        with patch("qebench.commands.export._REPO_ROOT", tmp_path):
            result = _xp_leaderboard()
        assert len(result) == 1
        assert result[0]["username"] == "good"

    def test_skips_unopenable_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        xp_dir = tmp_path / "results" / "xp"
        xp_dir.mkdir(parents=True)
        (xp_dir / "good.json").write_text(json.dumps({"total": 30, "actions": {}}))
        (xp_dir / "locked.json").write_text(json.dumps({"total": 999, "actions": {}}))
        _break_open_for(monkeypatch, "locked.json")
        with patch("qebench.commands.export._REPO_ROOT", tmp_path):
            result = _xp_leaderboard()
        assert len(result) == 1
        assert result[0]["username"] == "good"

    def test_skips_non_numeric_total(self, tmp_path: Path) -> None:
        # A hand-edited file whose "total" is null or a string is valid JSON and a
        # valid object, so it reaches the `-x["total_xp"]` sort key and used to
        # raise TypeError there, losing the whole leaderboard, not just this file.
        xp_dir = tmp_path / "results" / "xp"
        xp_dir.mkdir(parents=True)
        (xp_dir / "good.json").write_text(json.dumps({"total": 30, "actions": {}}))
        (xp_dir / "null.json").write_text(json.dumps({"total": None}))
        (xp_dir / "text.json").write_text(json.dumps({"total": "lots", "actions": {}}))
        with patch("qebench.commands.export._REPO_ROOT", tmp_path):
            result = _xp_leaderboard()
        assert [r["username"] for r in result] == ["good"]

    def test_reads_file_with_utf8_bom(self, tmp_path: Path) -> None:
        # Windows editors prepend a BOM to otherwise valid UTF-8.  The file is
        # perfectly recoverable, so it must be read, not skipped as malformed.
        xp_dir = tmp_path / "results" / "xp"
        xp_dir.mkdir(parents=True)
        (xp_dir / "bom.json").write_bytes(
            b"\xef\xbb\xbf" + json.dumps({"total": 30, "actions": {"翻译": 5}}, ensure_ascii=False).encode("utf-8")
        )
        with patch("qebench.commands.export._REPO_ROOT", tmp_path):
            result = _xp_leaderboard()
        assert [r["username"] for r in result] == ["bom"]
        assert result[0]["total_xp"] == 30


class TestActivityFeed:
    def test_empty_no_dir(self, tmp_path: Path) -> None:
        with patch("qebench.commands.export._REPO_ROOT", tmp_path):
            result = _activity_feed()
        assert result == []

    def test_loads_jsonl(self, tmp_path: Path) -> None:
        tr_dir = tmp_path / "results" / "translations"
        tr_dir.mkdir(parents=True)
        lines = [
            json.dumps({"timestamp": "2025-01-01T10:00:00", "term_id": "term-001", "score": 0.8}),
            json.dumps({"timestamp": "2025-01-01T10:05:00", "term_id": "term-002", "score": 0.6}),
        ]
        (tr_dir / "alice.jsonl").write_text("\n".join(lines) + "\n")
        with patch("qebench.commands.export._REPO_ROOT", tmp_path):
            result = _activity_feed()
        assert len(result) == 2
        # Most recent first
        assert result[0]["timestamp"] == "2025-01-01T10:05:00"
        assert result[0]["username"] == "alice"

    def test_limits_to_50(self, tmp_path: Path) -> None:
        tr_dir = tmp_path / "results" / "translations"
        tr_dir.mkdir(parents=True)
        lines = [
            json.dumps({"timestamp": f"2025-01-01T{i:02d}:00:00", "score": 0.5})
            for i in range(60)
        ]
        (tr_dir / "user.jsonl").write_text("\n".join(lines) + "\n")
        with patch("qebench.commands.export._REPO_ROOT", tmp_path):
            result = _activity_feed()
        assert len(result) == 50

    def test_skips_malformed_line(self, tmp_path: Path) -> None:
        tr_dir = tmp_path / "results" / "translations"
        tr_dir.mkdir(parents=True)
        # A merge-conflict marker between two otherwise valid records (the
        # exact failure mode that broke CI in #28).
        lines = [
            json.dumps({"timestamp": "2025-01-01T10:00:00", "score": 0.8}),
            "<<<<<<< Updated upstream",
            json.dumps({"timestamp": "2025-01-01T10:05:00", "score": 0.6}),
        ]
        (tr_dir / "alice.jsonl").write_text("\n".join(lines) + "\n")
        with patch("qebench.commands.export._REPO_ROOT", tmp_path):
            result = _activity_feed()
        assert len(result) == 2
        assert {r["timestamp"] for r in result} == {
            "2025-01-01T10:00:00",
            "2025-01-01T10:05:00",
        }

    def test_skips_non_object_line(self, tmp_path: Path) -> None:
        tr_dir = tmp_path / "results" / "translations"
        tr_dir.mkdir(parents=True)
        # Valid JSON, but not an object — record["username"] = ... would raise.
        lines = [
            json.dumps({"timestamp": "2025-01-01T10:00:00", "score": 0.8}),
            json.dumps([1, 2, 3]),
            json.dumps("just a string"),
        ]
        (tr_dir / "alice.jsonl").write_text("\n".join(lines) + "\n")
        with patch("qebench.commands.export._REPO_ROOT", tmp_path):
            result = _activity_feed()
        assert len(result) == 1
        assert result[0]["timestamp"] == "2025-01-01T10:00:00"

    def test_skips_misencoded_file(self, tmp_path: Path) -> None:
        # A GBK save raises UnicodeDecodeError from the file *iterator*, so the
        # per-line json.loads guard never sees it — one bad file used to take
        # every other contributor's activity down with it.
        tr_dir = tmp_path / "results" / "translations"
        tr_dir.mkdir(parents=True)
        (tr_dir / "alice.jsonl").write_text(
            json.dumps({"timestamp": "2025-01-01T10:00:00", "score": 0.8}) + "\n"
        )
        _write_gbk(tr_dir / "bob.jsonl", {"timestamp": "2025-01-01T11:00:00", "zh": "术语"})
        with patch("qebench.commands.export._REPO_ROOT", tmp_path):
            result = _activity_feed()
        assert len(result) == 1
        assert result[0]["username"] == "alice"
        assert result[0]["timestamp"] == "2025-01-01T10:00:00"

    def test_keeps_records_read_before_decode_error(self, tmp_path: Path) -> None:
        # Padding pushes the valid records past the text-decoding chunk size so
        # they are yielded before the bad bytes are reached; they must survive.
        tr_dir = tmp_path / "results" / "translations"
        tr_dir.mkdir(parents=True)
        good = b"".join(
            (
                json.dumps({
                    "timestamp": f"2025-01-01T{i:02d}:00:00",
                    "score": 0.5,
                    "pad": "x" * 2000,
                })
                + "\n"
            ).encode("utf-8")
            for i in range(20)
        )
        (tr_dir / "alice.jsonl").write_bytes(
            good
            + json.dumps(
                {"timestamp": "2025-02-01T00:00:00", "zh": "术语"}, ensure_ascii=False
            ).encode("gbk")
        )
        with patch("qebench.commands.export._REPO_ROOT", tmp_path):
            result = _activity_feed()
        # Everything decoded before the bad bytes is kept; only the final line
        # may be lost with the chunk that failed to decode.
        assert 19 <= len(result) <= 20
        assert all(r["username"] == "alice" for r in result)
        assert all(r["timestamp"].startswith("2025-01-01T") for r in result)
        assert result == sorted(result, key=lambda r: r["timestamp"], reverse=True)

    def test_skips_unopenable_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        tr_dir = tmp_path / "results" / "translations"
        tr_dir.mkdir(parents=True)
        (tr_dir / "alice.jsonl").write_text(
            json.dumps({"timestamp": "2025-01-01T10:00:00", "score": 0.8}) + "\n"
        )
        (tr_dir / "locked.jsonl").write_text(
            json.dumps({"timestamp": "2025-01-01T11:00:00", "score": 0.9}) + "\n"
        )
        _break_open_for(monkeypatch, "locked.jsonl")
        with patch("qebench.commands.export._REPO_ROOT", tmp_path):
            result = _activity_feed()
        assert len(result) == 1
        assert result[0]["username"] == "alice"

    def test_tolerates_non_string_timestamp(self, tmp_path: Path) -> None:
        # A record with a null or numeric timestamp is a valid JSON object, so it
        # survives every per-line guard and reaches the sort, where comparing it
        # against a str used to raise TypeError and abort the whole export.
        tr_dir = tmp_path / "results" / "translations"
        tr_dir.mkdir(parents=True)
        (tr_dir / "alice.jsonl").write_text(
            json.dumps({"timestamp": "2025-01-01T10:00:00", "score": 0.8}) + "\n"
        )
        (tr_dir / "bob.jsonl").write_text(
            json.dumps({"timestamp": None, "score": 0.1}) + "\n"
            + json.dumps({"timestamp": 1735725600, "score": 0.2}) + "\n"
        )
        with patch("qebench.commands.export._REPO_ROOT", tmp_path):
            result = _activity_feed()
        # Nothing is dropped; the unusable timestamps sort last, as a missing one does.
        assert len(result) == 3
        assert result[0]["username"] == "alice"

    def test_reads_file_with_utf8_bom(self, tmp_path: Path) -> None:
        tr_dir = tmp_path / "results" / "translations"
        tr_dir.mkdir(parents=True)
        (tr_dir / "bom.jsonl").write_bytes(
            b"\xef\xbb\xbf"
            + (json.dumps({"timestamp": "2025-01-01T10:00:00", "zh": "术语"}, ensure_ascii=False) + "\n").encode(
                "utf-8"
            )
        )
        with patch("qebench.commands.export._REPO_ROOT", tmp_path):
            result = _activity_feed()
        assert [r["username"] for r in result] == ["bom"]
        assert result[0]["zh"] == "术语"


class TestTermSamples:
    def test_empty(self) -> None:
        assert _term_samples([]) == []

    def test_limits_per_domain(self) -> None:
        terms = [_make_term(f"term-{i:03d}", "economics") for i in range(10)]
        result = _term_samples(terms, per_domain=3)
        assert len(result) == 3

    def test_multiple_domains(self) -> None:
        terms = [
            _make_term("term-001", "economics"),
            _make_term("term-002", "economics"),
            _make_term("term-003", "finance"),
        ]
        result = _term_samples(terms, per_domain=2)
        assert len(result) == 3
        ids = {s["id"] for s in result}
        assert ids == {"term-001", "term-002", "term-003"}

    def test_output_format(self) -> None:
        terms = [_make_term("term-001", "economics", "advanced")]
        result = _term_samples(terms)
        assert result[0] == {
            "id": "term-001",
            "en": "term term-001",
            "zh": "术语term-001",
            "difficulty": "advanced",
        }


class TestExportIntegration:
    def test_writes_all_json_files(self, tmp_path: Path, sample_terms_file: Path) -> None:
        export_dir = tmp_path / "export"
        with (
            patch("qebench.commands.export.EXPORT_DIR", export_dir),
            patch("qebench.utils.dataset.DATA_DIR", sample_terms_file),
        ):
            export()

        expected_files = [
            "coverage.json",
            "domains.json",
            "difficulty.json",
            "leaderboard.json",
            "activity.json",
            "samples.json",
        ]
        for name in expected_files:
            path = export_dir / name
            assert path.exists(), f"Missing {name}"
            data = json.loads(path.read_text())
            assert data is not None

    def test_coverage_structure(self, tmp_path: Path, sample_terms_file: Path) -> None:
        export_dir = tmp_path / "export"
        with (
            patch("qebench.commands.export.EXPORT_DIR", export_dir),
            patch("qebench.utils.dataset.DATA_DIR", sample_terms_file),
        ):
            export()

        coverage = json.loads((export_dir / "coverage.json").read_text())
        assert "terms" in coverage
        assert "sentences" in coverage
        assert "paragraphs" in coverage
        assert coverage["terms"]["current"] == 2  # From sample_terms fixture
        assert "total" in coverage

    def test_succeeds_with_malformed_results(self, tmp_path: Path, sample_terms_file: Path) -> None:
        # A corrupt community submission (conflict marker + non-object line) must
        # not crash the whole export — the regression behind #28.
        repo_root = tmp_path / "repo"
        tr_dir = repo_root / "results" / "translations"
        tr_dir.mkdir(parents=True)
        (tr_dir / "alice.jsonl").write_text(
            json.dumps({"timestamp": "2025-01-01T10:00:00", "score": 0.8}) + "\n"
            "<<<<<<< Updated upstream\n"
            + json.dumps([1, 2, 3]) + "\n"
        )
        export_dir = tmp_path / "export"
        with (
            patch("qebench.commands.export.EXPORT_DIR", export_dir),
            patch("qebench.commands.export._REPO_ROOT", repo_root),
            patch("qebench.utils.dataset.DATA_DIR", sample_terms_file),
        ):
            export()  # must not raise

        activity = json.loads((export_dir / "activity.json").read_text())
        assert len(activity) == 1
        assert activity[0]["timestamp"] == "2025-01-01T10:00:00"

    def test_succeeds_with_misencoded_results(self, tmp_path: Path, sample_terms_file: Path) -> None:
        # `qebench export` runs in the Deploy Docs workflow, so one contributor
        # file saved as GBK must not fail the dashboard build for everyone.
        repo_root = tmp_path / "repo"
        tr_dir = repo_root / "results" / "translations"
        tr_dir.mkdir(parents=True)
        xp_dir = repo_root / "results" / "xp"
        xp_dir.mkdir(parents=True)

        (tr_dir / "alice.jsonl").write_text(
            json.dumps({"timestamp": "2025-01-01T10:00:00", "score": 0.8}) + "\n"
        )
        _write_gbk(tr_dir / "bob.jsonl", {"timestamp": "2025-01-01T11:00:00", "zh": "术语"})
        (xp_dir / "alice.json").write_text(json.dumps({"total": 30, "actions": {}}))
        _write_gbk(xp_dir / "bob.json", {"total": 99, "actions": {"翻译": 5}})

        export_dir = tmp_path / "export"
        with (
            patch("qebench.commands.export.EXPORT_DIR", export_dir),
            patch("qebench.commands.export._REPO_ROOT", repo_root),
            patch("qebench.utils.dataset.DATA_DIR", sample_terms_file),
        ):
            export()  # must not raise

        activity = json.loads((export_dir / "activity.json").read_text())
        assert [r["username"] for r in activity] == ["alice"]
        leaderboard = json.loads((export_dir / "leaderboard.json").read_text())
        assert [r["username"] for r in leaderboard] == ["alice"]
