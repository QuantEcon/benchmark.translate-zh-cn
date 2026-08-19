"""Tests for judgment persistence and Elo updates."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qebench.scoring.judgments import (
    load_elo_ratings,
    record_consensus,
    record_judgment,
    save_elo_ratings,
    update_model_elos,
)
from qebench.scoring.ratings import load_judgment_records, recompute_elo


@pytest.fixture(autouse=True)
def judgments_dir(tmp_path, monkeypatch) -> Path:
    """Point JUDGMENTS_DIR at an empty directory for every test in this module.

    ``load_elo_ratings`` rebuilds from the judgment logs whenever elo.json is
    unusable, so without this a fallback would replay the repository's own
    committed judgments and the expected ratings would drift with the
    checkout.  Tests that want logs write into the directory returned here.
    """
    directory = tmp_path / "judgments"
    directory.mkdir()
    monkeypatch.setattr("qebench.scoring.judgments.JUDGMENTS_DIR", directory)
    return directory


def _judgment(model_a: str, model_b: str, winner: str, timestamp: str) -> dict:
    """A pairwise judgment record in the shape ``qebench judge`` writes."""
    return {
        "entry_id": "term-001",
        "model_a": model_a,
        "model_b": model_b,
        "winner": winner,
        "score_a": {"accuracy": 4, "fluency": 4},
        "score_b": {"accuracy": 3, "fluency": 3},
        "timestamp": timestamp,
        "cli_version": "0.3.2",
    }


def _write_log(directory: Path, username: str, records: list[dict]) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{username}.jsonl"
    with open(path, "a", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path


def _expected_rebuild(directory: Path) -> dict[str, float]:
    """What ratings.py makes of these logs — the contract the fallback must meet."""
    return {
        r.label: round(r.rating, 1)
        for r in recompute_elo(load_judgment_records(directory), by_prompt=True)
    }


class TestEloRatings:
    def test_no_cache_and_no_logs_is_empty(self, tmp_path, monkeypatch) -> None:
        """Nothing to load and nothing to rebuild from, so nobody has a rating yet."""
        monkeypatch.setattr("qebench.scoring.judgments.ELO_PATH", tmp_path / "elo.json")
        assert load_elo_ratings() == {}

    def test_no_cache_and_absent_log_directory_is_empty(self, tmp_path, monkeypatch) -> None:
        """A fresh checkout has neither file; the rebuild must not raise on the missing dir."""
        monkeypatch.setattr("qebench.scoring.judgments.ELO_PATH", tmp_path / "elo.json")
        monkeypatch.setattr("qebench.scoring.judgments.JUDGMENTS_DIR", tmp_path / "nowhere")
        assert load_elo_ratings() == {}

    def test_save_and_load(self, tmp_path, monkeypatch) -> None:
        elo_path = tmp_path / "elo.json"
        monkeypatch.setattr("qebench.scoring.judgments.ELO_PATH", elo_path)
        ratings = {"claude": 1520.0, "gpt-4o": 1480.0}
        save_elo_ratings(ratings)
        loaded = load_elo_ratings()
        assert loaded == ratings

    def test_update_model_elos_new_models(self, tmp_path, monkeypatch) -> None:
        elo_path = tmp_path / "elo.json"
        monkeypatch.setattr("qebench.scoring.judgments.ELO_PATH", elo_path)
        new_a, new_b = update_model_elos("claude", "gpt-4o", "a")
        # Winner gains, loser loses, starting from 1500
        assert new_a > 1500
        assert new_b < 1500

    def test_update_model_elos_tie(self, tmp_path, monkeypatch) -> None:
        elo_path = tmp_path / "elo.json"
        monkeypatch.setattr("qebench.scoring.judgments.ELO_PATH", elo_path)
        new_a, new_b = update_model_elos("claude", "gpt-4o", "tie")
        # Tie from equal ratings → no change
        assert new_a == 1500.0
        assert new_b == 1500.0

    def test_update_persists(self, tmp_path, monkeypatch) -> None:
        elo_path = tmp_path / "elo.json"
        monkeypatch.setattr("qebench.scoring.judgments.ELO_PATH", elo_path)
        update_model_elos("claude", "gpt-4o", "a")
        ratings = load_elo_ratings()
        assert "claude" in ratings
        assert "gpt-4o" in ratings

    def test_invalid_winner_raises(self, tmp_path, monkeypatch) -> None:
        elo_path = tmp_path / "elo.json"
        monkeypatch.setattr("qebench.scoring.judgments.ELO_PATH", elo_path)
        with pytest.raises(ValueError, match="Invalid winner"):
            update_model_elos("claude", "gpt-4o", "invalid")

    def test_update_model_elos_neither(self, tmp_path, monkeypatch) -> None:
        """'neither' is treated as tie for Elo calculation (#6)."""
        elo_path = tmp_path / "elo.json"
        monkeypatch.setattr("qebench.scoring.judgments.ELO_PATH", elo_path)
        new_a, new_b = update_model_elos("claude", "gpt-4o", "neither")
        # Neither from equal ratings → no change (same as tie)
        assert new_a == 1500.0
        assert new_b == 1500.0


class TestRebuildFromJudgments:
    """The committed logs are the source of truth, so a lost cache is recoverable."""

    def test_missing_cache_rebuilds_from_the_logs(
        self, tmp_path, monkeypatch, judgments_dir
    ) -> None:
        """An absent elo.json must not put everyone back on DEFAULT_RATING."""
        monkeypatch.setattr("qebench.scoring.judgments.ELO_PATH", tmp_path / "elo.json")
        _write_log(
            judgments_dir,
            "alice",
            [_judgment("claude:academic", "gpt-4o:academic", "a", "2026-04-02T12:00:00Z")],
        )
        assert load_elo_ratings() == {"claude:academic": 1516.0, "gpt-4o:academic": 1484.0}

    def test_rebuild_matches_recompute_elo(self, tmp_path, monkeypatch, judgments_dir) -> None:
        """The fallback must agree with ratings.py, not roll its own replay."""
        monkeypatch.setattr("qebench.scoring.judgments.ELO_PATH", tmp_path / "elo.json")
        _write_log(
            judgments_dir,
            "alice",
            [
                _judgment("claude:academic", "gpt-4o:academic", "a", "2026-04-02T12:00:00Z"),
                _judgment("claude:default", "gpt-4o:academic", "b", "2026-04-02T12:05:00Z"),
                _judgment("claude:academic", "claude:default", "tie", "2026-04-02T12:10:00Z"),
            ],
        )
        expected = _expected_rebuild(judgments_dir)
        assert len(expected) == 3
        assert load_elo_ratings() == expected

    def test_rebuild_keeps_labels_exactly_as_recorded(self, tmp_path, monkeypatch, judgments_dir) -> None:
        """The cache is keyed on whatever judge.py wrote, bare labels included.

        Ranking by prompt here would drop every bare-labelled judgment, and
        judge.py still writes one for any model output with no
        prompt_template — on such a dataset the rebuild would hand back an
        empty cache, which is the failure the rebuild exists to prevent.
        """
        monkeypatch.setattr("qebench.scoring.judgments.ELO_PATH", tmp_path / "elo.json")
        _write_log(
            judgments_dir,
            "alice",
            [
                _judgment("claude", "gpt-4o", "a", "2026-04-02T12:00:00Z"),
                _judgment("claude:academic", "gpt-4o:academic", "a", "2026-04-02T12:05:00Z"),
            ],
        )
        assert sorted(load_elo_ratings()) == [
            "claude", "claude:academic", "gpt-4o", "gpt-4o:academic",
        ]

    def test_rebuild_is_not_empty_when_every_label_is_bare(
        self, tmp_path, monkeypatch, judgments_dir
    ) -> None:
        """The regression that motivated the change, stated on its own."""
        monkeypatch.setattr("qebench.scoring.judgments.ELO_PATH", tmp_path / "elo.json")
        _write_log(
            judgments_dir,
            "alice",
            [_judgment("claude", "gpt-4o", "a", "2026-04-02T12:00:00Z")],
        )
        ratings = load_elo_ratings()
        assert sorted(ratings) == ["claude", "gpt-4o"]
        assert ratings["claude"] > 1500 > ratings["gpt-4o"]

    # All three fallback paths pay for the rebuild, so all three are checked:
    # the missing cache is the common case (elo.json is gitignored, so a fresh
    # checkout has none), the bad payload is the one with a second function
    # between the caller and the rebuild, and the unopenable file is the one
    # that reaches the rebuild straight from an except clause.
    @pytest.mark.parametrize("cache,lock", [(None, False), ("[1520.0, 1480.0]", False), ("{}", True)])
    def test_rebuild_reads_the_logs_once_per_call(
        self, tmp_path, monkeypatch, judgments_dir, cache, lock
    ) -> None:
        """load_elo_ratings runs once per judgment, so a rebuild must not re-walk the logs."""
        elo_path = tmp_path / "elo.json"
        if cache is not None:
            elo_path.write_text(cache, encoding="utf-8")
        monkeypatch.setattr("qebench.scoring.judgments.ELO_PATH", elo_path)
        _write_log(
            judgments_dir,
            "alice",
            [_judgment("claude:academic", "gpt-4o:academic", "a", "2026-04-02T12:00:00Z")],
        )

        calls: list[Path] = []

        def counting(directory):
            calls.append(directory)
            return load_judgment_records(directory)

        monkeypatch.setattr("qebench.scoring.judgments.load_judgment_records", counting)
        if lock:
            real_open = open

            def fail(path, *args, **kwargs):
                if str(path) == str(elo_path):
                    raise OSError("permission denied")
                return real_open(path, *args, **kwargs)

            monkeypatch.setattr("builtins.open", fail)
        assert load_elo_ratings() == {"claude:academic": 1516.0, "gpt-4o:academic": 1484.0}
        assert len(calls) == 1

    def test_rebuild_is_not_cached_between_calls(
        self, tmp_path, monkeypatch, judgments_dir
    ) -> None:
        """A session appends judgments as it goes, so a process-wide cache would go stale."""
        monkeypatch.setattr("qebench.scoring.judgments.ELO_PATH", tmp_path / "elo.json")
        _write_log(
            judgments_dir,
            "alice",
            [_judgment("claude:academic", "gpt-4o:academic", "a", "2026-04-02T12:00:00Z")],
        )
        first = load_elo_ratings()
        _write_log(
            judgments_dir,
            "alice",
            [_judgment("claude:academic", "gpt-4o:academic", "a", "2026-04-02T12:05:00Z")],
        )
        second = load_elo_ratings()
        assert second["claude:academic"] > first["claude:academic"]

    def test_valid_cache_is_returned_without_reading_the_logs(
        self, tmp_path, monkeypatch, judgments_dir
    ) -> None:
        """The healthy path is the hot path; it must not pay for the rebuild."""
        elo_path = tmp_path / "elo.json"
        elo_path.write_text('{"claude:academic": 1601.5, "gpt-4o:academic": 1398.5}', encoding="utf-8")
        monkeypatch.setattr("qebench.scoring.judgments.ELO_PATH", elo_path)
        _write_log(
            judgments_dir,
            "alice",
            [_judgment("claude:academic", "gpt-4o:academic", "b", "2026-04-02T12:00:00Z")],
        )

        def boom(directory):
            raise AssertionError("the judgment logs must not be read for a usable cache")

        monkeypatch.setattr("qebench.scoring.judgments.load_judgment_records", boom)
        assert load_elo_ratings() == {"claude:academic": 1601.5, "gpt-4o:academic": 1398.5}

    def test_update_model_elos_continues_from_the_rebuilt_ratings(
        self, tmp_path, monkeypatch, judgments_dir
    ) -> None:
        """The point of the rebuild: the next judgment builds on history, not on 1500."""
        elo_path = tmp_path / "elo.json"
        monkeypatch.setattr("qebench.scoring.judgments.ELO_PATH", elo_path)
        _write_log(
            judgments_dir,
            "alice",
            [_judgment("claude:academic", "gpt-4o:academic", "a", "2026-04-02T12:00:00Z")],
        )

        new_a, new_b = update_model_elos("claude:academic", "gpt-4o:academic", "a")

        # Starting from the rebuilt 1516.0/1484.0, not from 1500.0 — which
        # would have produced 1516.0/1484.0 all over again.
        assert new_a == pytest.approx(1530.5, abs=0.05)
        assert new_b == pytest.approx(1469.5, abs=0.05)
        assert json.loads(elo_path.read_text(encoding="utf-8")) == {
            "claude:academic": new_a,
            "gpt-4o:academic": new_b,
        }


class TestCorruptEloFile:
    """elo.json is a rebuildable local cache — a bad one must not stop judging."""

    def test_undecodable_file_is_not_fatal(self, tmp_path, monkeypatch) -> None:
        """A cache saved as GBK rather than UTF-8 is rebuilt from, not fatal.

        UnicodeDecodeError subclasses ValueError, so neither an OSError nor a
        JSONDecodeError handler would catch it.  With no logs here there is
        nothing to rebuild, so the rebuild is empty.
        """
        elo_path = tmp_path / "elo.json"
        elo_path.write_bytes(
            json.dumps({"claude": 1520.0, "备注": 1480.0}, ensure_ascii=False).encode("gbk")
        )
        monkeypatch.setattr("qebench.scoring.judgments.ELO_PATH", elo_path)
        assert load_elo_ratings() == {}

    def test_truncated_file_is_not_fatal(self, tmp_path, monkeypatch) -> None:
        elo_path = tmp_path / "elo.json"
        elo_path.write_text('{"claude": 152')
        monkeypatch.setattr("qebench.scoring.judgments.ELO_PATH", elo_path)
        assert load_elo_ratings() == {}

    def test_non_object_json_is_not_fatal(self, tmp_path, monkeypatch) -> None:
        """A top-level list parses fine but has no .get for update_model_elos."""
        elo_path = tmp_path / "elo.json"
        elo_path.write_text("[1520.0, 1480.0]")
        monkeypatch.setattr("qebench.scoring.judgments.ELO_PATH", elo_path)
        assert load_elo_ratings() == {}

    def test_unreadable_file_is_not_fatal(self, tmp_path, monkeypatch) -> None:
        elo_path = tmp_path / "elo.json"
        elo_path.write_text(json.dumps({"claude": 1520.0}))
        monkeypatch.setattr("qebench.scoring.judgments.ELO_PATH", elo_path)

        def fail(path, *args, **kwargs):
            raise OSError("permission denied")

        monkeypatch.setattr("builtins.open", fail)
        assert load_elo_ratings() == {}

    def test_undecodable_cache_rebuilds_rather_than_resetting(
        self, tmp_path, monkeypatch, judgments_dir
    ) -> None:
        """The quarantined file's ratings are recovered from the logs, not discarded."""
        elo_path = tmp_path / "elo.json"
        elo_path.write_bytes(
            json.dumps({"claude:academic": 1520.0, "备注": 1480.0}, ensure_ascii=False).encode("gbk")
        )
        monkeypatch.setattr("qebench.scoring.judgments.ELO_PATH", elo_path)
        _write_log(
            judgments_dir,
            "alice",
            [_judgment("claude:academic", "gpt-4o:academic", "a", "2026-04-02T12:00:00Z")],
        )

        assert load_elo_ratings() == {"claude:academic": 1516.0, "gpt-4o:academic": 1484.0}
        assert len(list(tmp_path.glob("elo.json.corrupt*"))) == 1

    def test_unopenable_cache_rebuilds_and_leaves_the_file(
        self, tmp_path, monkeypatch, judgments_dir
    ) -> None:
        """A locked cache is left alone, but the session still gets real ratings."""
        elo_path = tmp_path / "elo.json"
        elo_path.write_text('{"claude:academic": 1700.0}', encoding="utf-8")
        monkeypatch.setattr("qebench.scoring.judgments.ELO_PATH", elo_path)
        _write_log(
            judgments_dir,
            "alice",
            [_judgment("claude:academic", "gpt-4o:academic", "a", "2026-04-02T12:00:00Z")],
        )

        real_open = open

        def fail(path, *args, **kwargs):
            if str(path) == str(elo_path):
                raise OSError("permission denied")
            return real_open(path, *args, **kwargs)

        monkeypatch.setattr("builtins.open", fail)
        assert load_elo_ratings() == {"claude:academic": 1516.0, "gpt-4o:academic": 1484.0}
        assert elo_path.read_text(encoding="utf-8") == '{"claude:academic": 1700.0}'

    def test_update_model_elos_survives_undecodable_cache(self, tmp_path, monkeypatch) -> None:
        """With no logs to rebuild from, ratings restart from DEFAULT_RATING."""
        elo_path = tmp_path / "elo.json"
        elo_path.write_bytes(
            json.dumps({"claude": 1520.0, "备注": 1480.0}, ensure_ascii=False).encode("gbk")
        )
        monkeypatch.setattr("qebench.scoring.judgments.ELO_PATH", elo_path)
        new_a, new_b = update_model_elos("claude", "gpt-4o", "a")
        assert new_a > 1500
        assert new_b < 1500

    def test_unreadable_cache_is_preserved_not_overwritten(self, tmp_path, monkeypatch) -> None:
        """The ratings are rebuildable; this particular file's bytes are not.

        It may hold a hand-edit or a label the logs never mention, and a
        misencoded file is one re-encode from readable — so the next save
        must not silently write over it.
        """
        elo_path = tmp_path / "elo.json"
        original = json.dumps({"claude": 1700.0, "通义千问": 1550.0}, ensure_ascii=False).encode("gbk")
        elo_path.write_bytes(original)
        monkeypatch.setattr("qebench.scoring.judgments.ELO_PATH", elo_path)

        update_model_elos("claude", "gpt-4o", "a")

        quarantined = list(tmp_path.glob("elo.json.corrupt*"))
        assert len(quarantined) == 1
        assert quarantined[0].read_bytes() == original
        assert json.loads(quarantined[0].read_bytes().decode("gbk"))["通义千问"] == 1550.0

    def test_repeat_corruption_does_not_clobber_the_first_quarantine(
        self, tmp_path, monkeypatch
    ) -> None:
        elo_path = tmp_path / "elo.json"
        monkeypatch.setattr("qebench.scoring.judgments.ELO_PATH", elo_path)

        elo_path.write_bytes(json.dumps({"claude": 1700.0}).encode("gbk") + b"\xff")
        load_elo_ratings()
        elo_path.write_text("{not json", encoding="utf-8")
        load_elo_ratings()

        assert sorted(p.name for p in tmp_path.glob("elo.json.corrupt*")) == [
            "elo.json.corrupt",
            "elo.json.corrupt.1",
        ]

    def test_unopenable_cache_is_left_in_place(self, tmp_path, monkeypatch) -> None:
        """A file we merely failed to open may be healthy and only briefly locked.

        Renaming it away would be worse than rebuilding, so only a bad
        *payload* gets quarantined.
        """
        elo_path = tmp_path / "elo.json"
        elo_path.write_text('{"claude": 1700.0}', encoding="utf-8")
        monkeypatch.setattr("qebench.scoring.judgments.ELO_PATH", elo_path)

        real_open = open

        def fail(path, *args, **kwargs):
            if str(path) == str(elo_path):
                raise OSError("permission denied")
            return real_open(path, *args, **kwargs)

        monkeypatch.setattr("builtins.open", fail)
        assert load_elo_ratings() == {}
        assert elo_path.exists()
        assert elo_path.read_text(encoding="utf-8") == '{"claude": 1700.0}'
        assert list(tmp_path.glob("elo.json.corrupt*")) == []

    def test_non_numeric_rating_is_rejected_and_preserved(self, tmp_path, monkeypatch) -> None:
        """Raised on #33: the dict guard passed, then update_elo did arithmetic on a str."""
        elo_path = tmp_path / "elo.json"
        original = '{"claude": "1700", "gpt-4o": 1600.0}'
        elo_path.write_text(original, encoding="utf-8")
        monkeypatch.setattr("qebench.scoring.judgments.ELO_PATH", elo_path)

        assert load_elo_ratings() == {}
        quarantined = list(tmp_path.glob("elo.json.corrupt*"))
        assert len(quarantined) == 1
        assert quarantined[0].read_text(encoding="utf-8") == original

    def test_boolean_rating_is_rejected(self, tmp_path, monkeypatch) -> None:
        """bool subclasses int, so True would otherwise sort and compute as 1."""
        elo_path = tmp_path / "elo.json"
        elo_path.write_text('{"claude": true}', encoding="utf-8")
        monkeypatch.setattr("qebench.scoring.judgments.ELO_PATH", elo_path)
        assert load_elo_ratings() == {}

    def test_update_model_elos_survives_non_numeric_rating(self, tmp_path, monkeypatch) -> None:
        """The end-to-end path Copilot described: a hand-edit crashed the judgment."""
        elo_path = tmp_path / "elo.json"
        elo_path.write_text('{"claude": "1700"}', encoding="utf-8")
        monkeypatch.setattr("qebench.scoring.judgments.ELO_PATH", elo_path)
        new_a, new_b = update_model_elos("claude", "gpt-4o", "a")
        assert new_a > 1500
        assert new_b < 1500

    def test_all_numeric_ratings_are_kept(self, tmp_path, monkeypatch) -> None:
        """The guard must not reject healthy caches — ints and floats both pass."""
        elo_path = tmp_path / "elo.json"
        elo_path.write_text('{"claude": 1700, "gpt-4o": 1600.5}', encoding="utf-8")
        monkeypatch.setattr("qebench.scoring.judgments.ELO_PATH", elo_path)
        assert load_elo_ratings() == {"claude": 1700, "gpt-4o": 1600.5}
        assert list(tmp_path.glob("elo.json.corrupt*")) == []

    def test_non_object_cache_is_also_preserved(self, tmp_path, monkeypatch) -> None:
        """Valid JSON of the wrong shape is still someone's file — keep it."""
        elo_path = tmp_path / "elo.json"
        elo_path.write_text("[1520.0, 1480.0]", encoding="utf-8")
        monkeypatch.setattr("qebench.scoring.judgments.ELO_PATH", elo_path)

        assert load_elo_ratings() == {}
        quarantined = list(tmp_path.glob("elo.json.corrupt*"))
        assert len(quarantined) == 1
        assert quarantined[0].read_text(encoding="utf-8") == "[1520.0, 1480.0]"

    def test_update_model_elos_survives_non_object_cache(self, tmp_path, monkeypatch) -> None:
        elo_path = tmp_path / "elo.json"
        elo_path.write_text("[1520.0, 1480.0]")
        monkeypatch.setattr("qebench.scoring.judgments.ELO_PATH", elo_path)
        new_a, new_b = update_model_elos("claude", "gpt-4o", "b")
        assert new_a < 1500
        assert new_b > 1500


class TestRecordJudgment:
    def test_saves_jsonl(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr("qebench.scoring.judgments.JUDGMENTS_DIR", tmp_path)
        record_judgment(
            username="testuser",
            entry_id="term-001",
            model_a="claude",
            model_b="gpt-4o",
            winner="a",
            score_a_accuracy=4,
            score_a_fluency=5,
            score_b_accuracy=3,
            score_b_fluency=3,
            timestamp="2026-04-02T12:00:00Z",
            cli_version="0.3.0",
        )
        path = tmp_path / "testuser.jsonl"
        assert path.exists()
        records = [json.loads(ln) for ln in path.read_text().splitlines() if ln.strip()]
        assert len(records) == 1
        assert records[0]["entry_id"] == "term-001"
        assert records[0]["winner"] == "a"
        assert records[0]["score_a"]["accuracy"] == 4

    def test_appends_multiple(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr("qebench.scoring.judgments.JUDGMENTS_DIR", tmp_path)
        for i in range(3):
            record_judgment(
                username="testuser",
                entry_id=f"term-{i:03d}",
                model_a="claude",
                model_b="gpt-4o",
                winner="b",
                score_a_accuracy=3,
                score_a_fluency=3,
                score_b_accuracy=4,
                score_b_fluency=5,
                timestamp="2026-04-02T12:00:00Z",
                cli_version="0.3.0",
            )
        path = tmp_path / "testuser.jsonl"
        records = [json.loads(ln) for ln in path.read_text().splitlines() if ln.strip()]
        assert len(records) == 3

    def test_creates_directory(self, tmp_path, monkeypatch) -> None:
        out_dir = tmp_path / "nested" / "judgments"
        monkeypatch.setattr("qebench.scoring.judgments.JUDGMENTS_DIR", out_dir)
        record_judgment(
            username="testuser",
            entry_id="term-001",
            model_a="claude",
            model_b="gpt-4o",
            winner="tie",
            score_a_accuracy=3,
            score_a_fluency=3,
            score_b_accuracy=3,
            score_b_fluency=3,
            timestamp="2026-04-02T12:00:00Z",
            cli_version="0.3.0",
        )
        assert (out_dir / "testuser.jsonl").exists()

    def test_suggestion_stored(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr("qebench.scoring.judgments.JUDGMENTS_DIR", tmp_path)
        record_judgment(
            username="testuser",
            entry_id="term-001",
            model_a="claude",
            model_b="gpt-4o",
            winner="neither",
            score_a_accuracy=None,
            score_a_fluency=None,
            score_b_accuracy=None,
            score_b_fluency=None,
            suggestion="更好的翻译",
            timestamp="2026-04-02T12:00:00Z",
            cli_version="0.3.2",
        )
        records = [json.loads(ln) for ln in (tmp_path / "testuser.jsonl").read_text().splitlines()]
        assert records[0]["suggestion"] == "更好的翻译"

    def test_empty_suggestion_omitted(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr("qebench.scoring.judgments.JUDGMENTS_DIR", tmp_path)
        record_judgment(
            username="testuser",
            entry_id="term-001",
            model_a="claude",
            model_b="gpt-4o",
            winner="tie",
            score_a_accuracy=None,
            score_a_fluency=None,
            score_b_accuracy=None,
            score_b_fluency=None,
            timestamp="2026-04-02T12:00:00Z",
            cli_version="0.3.2",
        )
        records = [json.loads(ln) for ln in (tmp_path / "testuser.jsonl").read_text().splitlines()]
        assert "suggestion" not in records[0]


class TestRecordConsensus:
    def test_saves_consensus(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr("qebench.scoring.judgments.JUDGMENTS_DIR", tmp_path)
        record_consensus(
            username="testuser",
            entry_id="term-001",
            models=["claude:default", "claude:academic"],
            translation="\u901a\u8d27\u81a8\u80c0",
            accuracy=5,
            fluency=4,
            suggestion="",
            timestamp="2026-04-07T12:00:00Z",
            cli_version="0.3.2",
        )
        path = tmp_path / "testuser.jsonl"
        assert path.exists()
        records = [json.loads(ln) for ln in path.read_text().splitlines() if ln.strip()]
        assert len(records) == 1
        assert records[0]["type"] == "consensus"
        assert records[0]["accuracy"] == 5
        assert records[0]["models"] == ["claude:default", "claude:academic"]

    def test_with_suggestion(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr("qebench.scoring.judgments.JUDGMENTS_DIR", tmp_path)
        record_consensus(
            username="testuser",
            entry_id="term-008",
            models=["claude:default"],
            translation="\u6210\u672c\u51fd\u6570",
            accuracy=1,
            fluency=3,
            suggestion="\u4ee3\u4ef7\u51fd\u6570",
            timestamp="2026-04-07T12:00:00Z",
            cli_version="0.3.2",
        )
        records = [json.loads(ln) for ln in (tmp_path / "testuser.jsonl").read_text().splitlines()]
        assert records[0]["suggestion"] == "\u4ee3\u4ef7\u51fd\u6570"

    def test_invalid_accuracy_raises(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr("qebench.scoring.judgments.JUDGMENTS_DIR", tmp_path)
        with pytest.raises(ValueError, match="accuracy"):
            record_consensus(
                username="testuser",
                entry_id="term-001",
                models=["claude:default"],
                translation="通货膨胀",
                accuracy=6,
                fluency=3,
                timestamp="2026-04-07T12:00:00Z",
                cli_version="0.3.2",
            )

    def test_invalid_fluency_raises(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr("qebench.scoring.judgments.JUDGMENTS_DIR", tmp_path)
        with pytest.raises(ValueError, match="fluency"):
            record_consensus(
                username="testuser",
                entry_id="term-001",
                models=["claude:default"],
                translation="通货膨胀",
                accuracy=3,
                fluency=-1,
                timestamp="2026-04-07T12:00:00Z",
                cli_version="0.3.2",
            )
