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
    _file_summary,
    _model_comparison,
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


def _judgment(**fields: object) -> str:
    """One judgment record as a JSONL line, in the shape ``qebench judge`` writes.

    Defaults describe a current pairwise judgment where both sides carry a
    prompt and scores are on the 0-5 scale; pass ``model_a``, ``winner``,
    ``cli_version`` and friends to move it to another era or outcome.
    """
    record: dict = {
        "entry_id": "term-001",
        "model_a": "claude-sonnet-4-6:academic",
        "model_b": "claude-haiku-4-5-20251001:academic",
        "winner": "a",
        "score_a": {"accuracy": 5, "fluency": 4},
        "score_b": {"accuracy": 3, "fluency": 3},
        "translation_a": "贝尔曼方程",
        "translation_b": "贝尔曼等式",
        "timestamp": "2026-04-07T00:00:00+00:00",
        "cli_version": "0.5.0",
    }
    record.update(fields)
    return json.dumps(record, ensure_ascii=False)


def _write_judgments(repo_root: Path, username: str, lines: list[str]) -> None:
    judgments_dir = repo_root / "results" / "judgments"
    judgments_dir.mkdir(parents=True, exist_ok=True)
    (judgments_dir / f"{username}.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _run_export(repo_root: Path, export_dir: Path, data_dir: Path) -> None:
    """Run the full export against a throwaway repo root."""
    with (
        patch("qebench.commands.export.EXPORT_DIR", export_dir),
        patch("qebench.commands.export._REPO_ROOT", repo_root),
        patch("qebench.utils.dataset.DATA_DIR", data_dir),
    ):
        export()


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


class TestCopilotFollowUps:
    """Raised on #33: 'actions' was forwarded to the dashboard unvalidated."""

    def test_non_object_actions_becomes_empty_breakdown(self, tmp_path: Path) -> None:
        """index.html does Object.entries(user.actions || {}); a JS string is truthy.

        Left alone, "oops" renders on the live dashboard as "0: o . 1: o . 2: p".
        The breakdown is cosmetic, so the contributor keeps their place.
        """
        xp_dir = tmp_path / "results" / "xp"
        xp_dir.mkdir(parents=True)
        (xp_dir / "alice.json").write_text(
            json.dumps({"total": 150, "actions": "oops"}), encoding="utf-8"
        )
        with patch("qebench.commands.export._REPO_ROOT", tmp_path):
            result = _xp_leaderboard()
        assert len(result) == 1
        assert result[0]["username"] == "alice"
        assert result[0]["total_xp"] == 150
        assert result[0]["actions"] == {}

    def test_null_actions_becomes_empty_breakdown(self, tmp_path: Path) -> None:
        xp_dir = tmp_path / "results" / "xp"
        xp_dir.mkdir(parents=True)
        (xp_dir / "alice.json").write_text(
            json.dumps({"total": 10, "actions": None}), encoding="utf-8"
        )
        with patch("qebench.commands.export._REPO_ROOT", tmp_path):
            result = _xp_leaderboard()
        assert result[0]["actions"] == {}

    def test_valid_actions_are_untouched(self, tmp_path: Path) -> None:
        xp_dir = tmp_path / "results" / "xp"
        xp_dir.mkdir(parents=True)
        (xp_dir / "alice.json").write_text(
            json.dumps({"total": 10, "actions": {"translate": 10}}), encoding="utf-8"
        )
        with patch("qebench.commands.export._REPO_ROOT", tmp_path):
            result = _xp_leaderboard()
        assert result[0]["actions"] == {"translate": 10}


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


class TestFileSummary:
    """The panel line each export prints."""

    def test_list_counts_entries(self) -> None:
        assert _file_summary([1, 2, 3]) == "3 entries"

    def test_dict_with_total_reports_it(self) -> None:
        assert _file_summary({"terms": {}, "total": 411}) == "411 total entries"

    def test_flat_dict_falls_back_to_key_count(self) -> None:
        # difficulty.json is a dict of plain counts; there is nothing better to say.
        assert _file_summary({"basic": 1, "intermediate": 2, "advanced": 0}) == "3 keys"

    def test_dict_of_collections_names_each_section(self) -> None:
        # ratings.json carries five sections; "5 keys" tells a reader nothing
        # about how much evidence is behind the ratings.
        summary = _file_summary({
            "by_model": [{"label": "a"}, {"label": "b"}],
            "scores_by_model": {"a": {}, "b": {}, "c": {}},
            "judgments": {"total": 21, "elo_eligible_by_model": 12},
        })
        assert summary == "by_model 2, scores_by_model 3, judgments 21"

    def test_non_collection_says_exported(self) -> None:
        assert _file_summary("something") == "exported"


class TestRatingsExport:
    """ratings.json — the recomputed ratings the dashboard reads.

    results/elo.json is gitignored, so the only ratings that can reach the
    site are the ones CI rebuilds from the committed judgment logs.
    """

    def test_writes_all_sections(self, tmp_path: Path, sample_terms_file: Path) -> None:
        repo_root = tmp_path / "repo"
        _write_judgments(repo_root, "mmcky", [_judgment()])
        export_dir = tmp_path / "export"
        _run_export(repo_root, export_dir, sample_terms_file)

        ratings = json.loads((export_dir / "ratings.json").read_text(encoding="utf-8"))
        assert set(ratings) == {
            "by_model",
            "by_model_prompt",
            "scores_by_model",
            "scores_by_model_prompt",
            "judgments",
        }

    def test_recomputes_ratings_from_records(self, tmp_path: Path, sample_terms_file: Path) -> None:
        """Three real-shaped records, one from each era the logs contain."""
        repo_root = tmp_path / "repo"
        _write_judgments(
            repo_root,
            "mmcky",
            [
                # v0.3-era, both sides prompted: rated at both granularities.
                _judgment(),
                # Against the human reference: scored, never rated.
                _judgment(
                    entry_id="term-002",
                    model_b="human-reference",
                    winner="b",
                    score_a={"accuracy": 4, "fluency": 4},
                    score_b={"accuracy": 5, "fluency": 5},
                    timestamp="2026-04-07T00:01:00+00:00",
                ),
                # v0.2-era bare labels on the 1-10 scale: only the by-model
                # ranking can use them, and the scores need rescaling.
                _judgment(
                    entry_id="term-003",
                    model_a="claude-sonnet-4-6",
                    model_b="claude-haiku-4-5-20251001",
                    winner="tie",
                    score_a={"accuracy": 10, "fluency": 10},
                    score_b={"accuracy": 10, "fluency": 10},
                    timestamp="2026-04-02T00:00:00+00:00",
                    cli_version="0.2.1",
                ),
            ],
        )
        export_dir = tmp_path / "export"
        _run_export(repo_root, export_dir, sample_terms_file)

        ratings = json.loads((export_dir / "ratings.json").read_text(encoding="utf-8"))

        # Prompted ranking sees the one prompted head-to-head: a clean win
        # from 1500 apiece moves both by half the K-factor.
        assert ratings["by_model_prompt"] == [
            {
                "label": "claude-sonnet-4-6:academic",
                "rating": 1516.0,
                "matches": 1,
                "wins": 1,
                "losses": 0,
                "ties": 0,
            },
            {
                "label": "claude-haiku-4-5-20251001:academic",
                "rating": 1484.0,
                "matches": 1,
                "wins": 0,
                "losses": 1,
                "ties": 0,
            },
        ]
        # Stripping prompts folds the v0.2 tie in: same ratings, one more match.
        assert ratings["by_model"] == [
            {
                "label": "claude-sonnet-4-6",
                "rating": 1516.0,
                "matches": 2,
                "wins": 1,
                "losses": 0,
                "ties": 1,
            },
            {
                "label": "claude-haiku-4-5-20251001",
                "rating": 1484.0,
                "matches": 2,
                "wins": 0,
                "losses": 1,
                "ties": 1,
            },
        ]

        # Scores include the human-reference record and the rescaled v0.2 one:
        # a 10 on the old scale is a 5 on the new.
        assert ratings["scores_by_model"] == {
            "claude-sonnet-4-6": {"accuracy": 4.67, "fluency": 4.33, "rated": 3},
            "claude-haiku-4-5-20251001": {"accuracy": 4.0, "fluency": 4.0, "rated": 2},
        }
        assert ratings["scores_by_model_prompt"] == {
            "claude-sonnet-4-6:academic": {"accuracy": 4.5, "fluency": 4.0, "rated": 2},
            "claude-haiku-4-5-20251001:academic": {"accuracy": 3.0, "fluency": 3.0, "rated": 1},
        }

    def test_judgment_counts_match_the_records_supplied(
        self, tmp_path: Path, sample_terms_file: Path
    ) -> None:
        """The counts are how a reader tells a ranking from noise, so they
        have to describe the evidence actually loaded."""
        repo_root = tmp_path / "repo"
        _write_judgments(
            repo_root,
            "mmcky",
            [
                _judgment(),
                _judgment(entry_id="term-002", model_b="human-reference", winner="b"),
                _judgment(
                    entry_id="term-003",
                    model_a="claude-sonnet-4-6",
                    model_b="claude-haiku-4-5-20251001",
                    winner="tie",
                ),
            ],
        )
        _write_judgments(repo_root, "alice", [_judgment(entry_id="term-004", winner="b")])
        export_dir = tmp_path / "export"
        _run_export(repo_root, export_dir, sample_terms_file)

        ratings = json.loads((export_dir / "ratings.json").read_text(encoding="utf-8"))
        assert ratings["judgments"] == {
            "total": 4,
            # Everything but the human-reference record.
            "elo_eligible_by_model": 3,
            # ...minus the record whose labels carry no prompt.
            "elo_eligible_by_model_prompt": 2,
        }

    def test_missing_judgments_dir_yields_empty_ratings(
        self, tmp_path: Path, sample_terms_file: Path
    ) -> None:
        """A checkout with no judgments must still build the dashboard."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        export_dir = tmp_path / "export"
        _run_export(repo_root, export_dir, sample_terms_file)  # must not raise

        ratings = json.loads((export_dir / "ratings.json").read_text(encoding="utf-8"))
        assert ratings["by_model"] == []
        assert ratings["by_model_prompt"] == []
        assert ratings["scores_by_model"] == {}
        assert ratings["scores_by_model_prompt"] == {}
        assert ratings["judgments"]["total"] == 0
        # The rest of the export is unaffected.
        assert json.loads((export_dir / "coverage.json").read_text(encoding="utf-8"))["terms"][
            "current"
        ] == 2

    def test_empty_judgments_dir_yields_empty_ratings(
        self, tmp_path: Path, sample_terms_file: Path
    ) -> None:
        repo_root = tmp_path / "repo"
        (repo_root / "results" / "judgments").mkdir(parents=True)
        export_dir = tmp_path / "export"
        _run_export(repo_root, export_dir, sample_terms_file)  # must not raise

        ratings = json.loads((export_dir / "ratings.json").read_text(encoding="utf-8"))
        assert ratings["by_model"] == []
        assert ratings["by_model_prompt"] == []
        assert ratings["judgments"] == {
            "total": 0,
            "elo_eligible_by_model": 0,
            "elo_eligible_by_model_prompt": 0,
        }

    def test_survives_a_corrupt_judgments_log(
        self, tmp_path: Path, sample_terms_file: Path
    ) -> None:
        """Every other reader in the export is proof against a corrupt community
        file (#28); the judgment log is read by CI too, so it needs the same
        guarantee — one bad line must cost that line, not the dashboard."""
        repo_root = tmp_path / "repo"
        judgments_dir = repo_root / "results" / "judgments"
        judgments_dir.mkdir(parents=True)
        (judgments_dir / "mmcky.jsonl").write_text(
            _judgment() + "\n"
            "<<<<<<< Updated upstream\n"
            + json.dumps([1, 2, 3]) + "\n",
            encoding="utf-8",
        )
        # A whole file saved in another encoding must not cost the others either.
        _write_gbk(
            judgments_dir / "bob.jsonl",
            {"model_a": "m1:x", "model_b": "m2:x", "winner": "a", "translation_a": "贝尔曼方程"},
        )

        export_dir = tmp_path / "export"
        _run_export(repo_root, export_dir, sample_terms_file)  # must not raise

        ratings = json.loads((export_dir / "ratings.json").read_text(encoding="utf-8"))
        # Only the one valid record survives — the conflict marker, the non-object
        # line and the misencoded file are dropped, not counted.
        assert ratings["judgments"] == {
            "total": 1,
            "elo_eligible_by_model": 1,
            "elo_eligible_by_model_prompt": 1,
        }
        assert [r["label"] for r in ratings["by_model_prompt"]] == [
            "claude-sonnet-4-6:academic",
            "claude-haiku-4-5-20251001:academic",
        ]

    def test_cjk_survives_the_write(self, tmp_path: Path, sample_terms_file: Path) -> None:
        """Records are full of Chinese, and a prompt file may be named in it too.

        Written with ensure_ascii the dashboard would show \\u672c\\u5730...,
        so assert the bytes on disk, not just the round trip.
        """
        repo_root = tmp_path / "repo"
        _write_judgments(
            repo_root,
            "mmcky",
            [
                _judgment(
                    model_a="本地模型:学术",
                    model_b="claude-haiku-4-5-20251001:学术",
                    translation_a="贝尔曼方程",
                )
            ],
        )
        export_dir = tmp_path / "export"
        _run_export(repo_root, export_dir, sample_terms_file)

        raw = (export_dir / "ratings.json").read_text(encoding="utf-8")
        assert "本地模型:学术" in raw
        assert "\\u" not in raw

        ratings = json.loads(raw)
        assert ratings["by_model_prompt"][0]["label"] == "本地模型:学术"
        assert [r["label"] for r in ratings["by_model"]] == [
            "本地模型",
            "claude-haiku-4-5-20251001",
        ]
        assert "本地模型:学术" in ratings["scores_by_model_prompt"]


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
            "ratings.json",
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


def _run_record(
    entry_id: str,
    *,
    model: str = "claude-sonnet-4-6",
    prompt: str = "default",
    entry_type: str | None = "terms",
    source_text: str = "Bellman equation",
    translated_text: str = "贝尔曼方程",
    formatting: dict | None = None,
) -> dict:
    record = {
        "entry_id": entry_id,
        "source_text": source_text,
        "translated_text": translated_text,
        "model": model,
        "provider": "claude",
        "prompt_template": prompt,
    }
    if entry_type is not None:
        record["entry_type"] = entry_type
    if formatting is not None:
        record["formatting"] = formatting
    return record


def _write_runs(repo_root: Path, name: str, records: list[dict]) -> Path:
    outputs = repo_root / "results" / "model-outputs"
    outputs.mkdir(parents=True, exist_ok=True)
    path = outputs / f"{name}.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path


GLOSSARY = [{"en": "Bellman equation", "zh-cn": "贝尔曼方程"}]


class TestModelComparison:
    def test_no_run_directory(self, tmp_path: Path) -> None:
        with patch("qebench.commands.export._REPO_ROOT", tmp_path):
            with patch("qebench.commands.export.load_glossary", return_value=GLOSSARY):
                result = _model_comparison()

        assert result["runs"] == []
        assert result["records"] == 0

    def test_groups_by_model_prompt_and_type(self, tmp_path: Path) -> None:
        _write_runs(tmp_path, "runs", [
            _run_record("term-001"),
            _run_record("term-002"),
            _run_record("sent-001", entry_type="sentences"),
            _run_record("term-003", model="claude-haiku-4-5-20251001"),
        ])

        with patch("qebench.commands.export._REPO_ROOT", tmp_path):
            with patch("qebench.commands.export.load_glossary", return_value=GLOSSARY):
                result = _model_comparison()

        assert len(result["runs"]) == 3
        assert result["models"] == ["claude-haiku-4-5-20251001", "claude-sonnet-4-6"]
        assert result["entry_types"] == ["sentences", "terms"]
        terms_row = next(r for r in result["runs"] if r["model"] == "claude-sonnet-4-6" and r["entry_type"] == "terms")
        assert terms_row["records"] == 2

    def test_glossary_compliance_is_scored(self, tmp_path: Path) -> None:
        _write_runs(tmp_path, "runs", [
            _run_record("term-001", translated_text="贝尔曼方程"),
            _run_record("term-002", translated_text="贝尔曼等式"),
        ])

        with patch("qebench.commands.export._REPO_ROOT", tmp_path):
            with patch("qebench.commands.export.load_glossary", return_value=GLOSSARY):
                result = _model_comparison()

        row = result["runs"][0]
        assert row["glossary"]["scored"] == 2
        assert row["glossary"]["mean"] == 0.5

    def test_records_the_glossary_says_nothing_about_are_excluded(self, tmp_path: Path) -> None:
        """Counting them as compliant would report a made-up 100%."""
        _write_runs(tmp_path, "runs", [
            _run_record("term-001", translated_text="贝尔曼方程"),
            _run_record("term-002", source_text="Some unrelated phrase", translated_text="无关短语"),
        ])

        with patch("qebench.commands.export._REPO_ROOT", tmp_path):
            with patch("qebench.commands.export.load_glossary", return_value=GLOSSARY):
                result = _model_comparison()

        row = result["runs"][0]
        assert row["records"] == 2
        assert row["glossary"]["scored"] == 1
        assert row["glossary"]["mean"] == 1.0

    def test_a_run_with_nothing_scorable_reports_none_not_zero(self, tmp_path: Path) -> None:
        _write_runs(tmp_path, "runs", [_run_record("term-001", source_text="Unrelated", translated_text="无关")])

        with patch("qebench.commands.export._REPO_ROOT", tmp_path):
            with patch("qebench.commands.export.load_glossary", return_value=GLOSSARY):
                result = _model_comparison()

        assert result["runs"][0]["glossary"] == {"scored": 0, "mean": None}

    def test_an_unavailable_glossary_does_not_fail_the_export(self, tmp_path: Path) -> None:
        """load_glossary() returns [] when the fetch fails and there is no cache."""
        _write_runs(tmp_path, "runs", [_run_record("term-001")])

        with patch("qebench.commands.export._REPO_ROOT", tmp_path):
            with patch("qebench.commands.export.load_glossary", return_value=[]):
                result = _model_comparison()

        assert result["glossary_terms"] == 0
        assert result["runs"][0]["glossary"] == {"scored": 0, "mean": None}

    def test_stored_formatting_is_used(self, tmp_path: Path) -> None:
        stored = {
            "directive_balance": False,
            "fence_consistency": True,
            "code_block_integrity": True,
            "fullwidth_punctuation": 0.5,
            "directive_spacing": 1.0,
        }
        _write_runs(tmp_path, "runs", [_run_record("term-001", formatting=stored)])

        with patch("qebench.commands.export._REPO_ROOT", tmp_path):
            with patch("qebench.commands.export.load_glossary", return_value=GLOSSARY):
                result = _model_comparison()

        row = result["runs"][0]
        assert row["pass_rates"]["directive_balance"] == 0.0
        assert row["means"]["fullwidth_punctuation"] == 0.5

    def test_missing_formatting_is_computed_on_the_fly(self, tmp_path: Path) -> None:
        """The April runs predate the field and must stay comparable."""
        _write_runs(tmp_path, "runs", [_run_record("term-001")])

        with patch("qebench.commands.export._REPO_ROOT", tmp_path):
            with patch("qebench.commands.export.load_glossary", return_value=GLOSSARY):
                result = _model_comparison()

        assert result["runs"][0]["pass_rates"]["directive_balance"] == 100.0

    def test_entry_type_falls_back_to_the_id_prefix(self, tmp_path: Path) -> None:
        _write_runs(tmp_path, "runs", [_run_record("para-001", entry_type=None)])

        with patch("qebench.commands.export._REPO_ROOT", tmp_path):
            with patch("qebench.commands.export.load_glossary", return_value=GLOSSARY):
                result = _model_comparison()

        assert result["runs"][0]["entry_type"] == "paragraphs"

    def test_a_malformed_line_does_not_fail_the_build(self, tmp_path: Path) -> None:
        """export runs in the docs-deploy workflow — one bad line must not stop it."""
        path = _write_runs(tmp_path, "runs", [_run_record("term-001")])
        with open(path, "a", encoding="utf-8") as f:
            f.write("{not valid json\n")
            f.write('"a bare string"\n')
            f.write('{"no_entry_id": true}\n')

        with patch("qebench.commands.export._REPO_ROOT", tmp_path):
            with patch("qebench.commands.export.load_glossary", return_value=GLOSSARY):
                result = _model_comparison()

        assert result["records"] == 1

    def test_an_unreadable_file_is_skipped(self, tmp_path: Path) -> None:
        _write_runs(tmp_path, "good", [_run_record("term-001")])
        bad = tmp_path / "results" / "model-outputs" / "bad.jsonl"
        bad.write_bytes(json.dumps(_run_record("term-002"), ensure_ascii=False).encode("gbk") + b"\n")

        with patch("qebench.commands.export._REPO_ROOT", tmp_path):
            with patch("qebench.commands.export.load_glossary", return_value=GLOSSARY):
                result = _model_comparison()

        assert result["records"] == 1
