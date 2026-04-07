"""Tests for judgment persistence and Elo updates."""

from __future__ import annotations

import json

import pytest

from qebench.scoring.judgments import (
    load_elo_ratings,
    record_consensus,
    record_judgment,
    save_elo_ratings,
    update_model_elos,
)


class TestEloRatings:
    def test_load_empty(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr("qebench.scoring.judgments.ELO_PATH", tmp_path / "elo.json")
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
