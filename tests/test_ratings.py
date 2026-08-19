"""Tests for rebuilding ratings from the committed judgment logs.

Every record here is synthetic and written into ``tmp_path``.  The real
``results/judgments/`` grows every time somebody judges, so a test pinned to
its contents would go red on the next submission rather than on a real
regression.

The property under most of these tests is determinism: Elo is path dependent,
so the same logs must replay in the same order on every machine or the
dashboard would disagree with itself.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qebench.scoring.ratings import (
    HUMAN_REFERENCE,
    Rating,
    elo_eligible,
    load_judgment_records,
    normalise_score,
    parse_version,
    recompute_elo,
    record_scale_max,
    score_summary,
    strip_prompt,
)

# A decisive first match between two fresh competitors: K=32, both on 1500.
WIN, LOSS = 1516.0, 1484.0


def _judgment(**overrides: object) -> dict:
    """A pairwise judgment record in the shape ``record_judgment`` writes."""
    record: dict = {
        "entry_id": "term-001",
        "model_a": "model-a:default",
        "model_b": "model-b:default",
        "winner": "a",
        "score_a": {"accuracy": 4, "fluency": 4},
        "score_b": {"accuracy": 3, "fluency": 3},
        "timestamp": "2026-04-07T06:00:00+00:00",
        "cli_version": "0.5.0",
    }
    record.update(overrides)
    return record


def _consensus(**overrides: object) -> dict:
    """A consensus record in the shape ``record_consensus`` writes."""
    record: dict = {
        "type": "consensus",
        "entry_id": "term-001",
        "models": ["model-a:default", "model-b:default"],
        "translation": "贝尔曼方程",
        "accuracy": 4,
        "fluency": 5,
        "timestamp": "2026-04-07T06:00:00+00:00",
        "cli_version": "0.3.1",
    }
    record.update(overrides)
    return record


def _write_log(directory: Path, username: str, records: list[dict]) -> Path:
    """Write one user's ``.jsonl`` log, creating the directory if needed."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{username}.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path


def _reverse_glob(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make ``Path.glob`` hand back files in reverse-sorted order.

    Directory order is filesystem-defined and differs between machines, so
    reversing it is the only portable way to prove the loader imposes its own
    order rather than inheriting one.
    """
    real_glob = Path.glob

    def fake(self: Path, pattern: str, **kwargs: object) -> object:
        return iter(sorted(real_glob(self, pattern), reverse=True))

    monkeypatch.setattr(Path, "glob", fake)


class TestParseVersion:
    def test_three_part_version(self) -> None:
        assert parse_version("0.3.1") == (0, 3, 1)

    def test_two_part_version(self) -> None:
        assert parse_version("1.0") == (1, 0, 0)

    def test_junk_is_oldest(self) -> None:
        assert parse_version("unknown") == (0, 0, 0)

    def test_empty_is_oldest(self) -> None:
        assert parse_version("") == (0, 0, 0)

    def test_junk_reads_on_the_legacy_scale(self) -> None:
        """The real consequence of sorting as (0,): no silent rescaling."""
        assert normalise_score(10, 10) == 5.0

    def test_leading_letters_tolerated(self) -> None:
        # A leading "v" is not a decimal digit, so parsing stops at once.
        assert parse_version("v0.3.1") == (0, 0, 0)

    def test_parsing_stops_at_a_chunk_with_no_digits(self) -> None:
        """Half a version is not glued back together out of the surviving parts."""
        assert parse_version("1.x.2") == (1, 0, 0)


class TestRecordScaleMax:
    """Which scale a record used is read from its scores, not its stamp.

    `cli_version` records the last *released* version, not the running code:
    this repo's log holds v0.4.0-only consensus records stamped 0.3.1.
    """

    def test_score_above_five_proves_the_old_scale(self) -> None:
        record = _judgment(score_a={"accuracy": 9, "fluency": 9}, cli_version="0.5.0")
        assert record_scale_max(record) == 10

    def test_a_zero_proves_the_new_scale(self) -> None:
        """0 is impossible on a 1-10 scale, so it outranks an old stamp."""
        record = _judgment(score_a={"accuracy": 0, "fluency": 3}, cli_version="0.2.1")
        assert record_scale_max(record) == 5

    def test_consensus_proves_the_new_scale(self) -> None:
        """Consensus shipped in the same release as the 0-5 scale.

        The real records this fixes are stamped 0.3.1 and score 5; trusting
        the stamp would rescale them to 2.22.
        """
        assert record_scale_max(_consensus(accuracy=5, fluency=5, cli_version="0.3.1")) == 5

    def test_version_breaks_the_tie_when_scores_are_ambiguous(self) -> None:
        """1-5 is legal on both scales, so nothing but the stamp is left."""
        assert record_scale_max(_judgment(score_a={"accuracy": 3}, cli_version="0.3.1")) == 10
        assert record_scale_max(_judgment(score_a={"accuracy": 3}, cli_version="0.4.0")) == 5

    def test_released_v031_is_the_old_scale(self) -> None:
        """Released 0.3.1 offered range(1, 11) and prompted 'Accuracy (1-10)'."""
        assert record_scale_max(_judgment(score_a={"accuracy": 4}, cli_version="0.3.1")) == 10

    def test_scoreless_record_falls_back_to_the_stamp(self) -> None:
        record = _judgment(score_a={"accuracy": None, "fluency": None},
                           score_b={"accuracy": None, "fluency": None},
                           cli_version="0.5.0")
        assert record_scale_max(record) == 5


class TestNormaliseScore:
    def test_old_scale_bottom(self) -> None:
        assert normalise_score(1, 10) == 0.0

    def test_old_scale_top(self) -> None:
        assert normalise_score(10, 10) == 5.0

    def test_old_scale_by_position(self) -> None:
        """9 of 10 is 4.44 of 5, not 4.5 — the map is by position in the range."""
        assert normalise_score(9, 10) == pytest.approx(40 / 9)
        assert round(normalise_score(9, 10), 2) == 4.44

    def test_boundary_release_passes_through(self) -> None:
        assert normalise_score(5, 5) == 5.0

    def test_same_value_either_side_of_the_boundary(self) -> None:
        """A 4 is rescaled before v0.3.0 and left alone from it."""
        assert normalise_score(4, 10) == pytest.approx(5 / 3)
        assert normalise_score(4, 5) == 4.0

    def test_zero_survives_on_the_new_scale(self) -> None:
        """0 is a legal 0-5 score and must not be read as missing."""
        assert normalise_score(0, 5) == 0.0

    def test_none_returns_none(self) -> None:
        """judge.py records None on both sides for a 'neither' verdict."""
        assert normalise_score(None, 5) is None

    def test_string_returns_none(self) -> None:
        assert normalise_score("4", 5) is None

    def test_true_returns_none(self) -> None:
        """bool subclasses int, so True would otherwise score as a 1."""
        assert normalise_score(True, 5) is None

    def test_false_returns_none(self) -> None:
        assert normalise_score(False, 5) is None

    def test_float_input_stays_float(self) -> None:
        assert normalise_score(3, 5) == 3.0
        assert isinstance(normalise_score(3, 5), float)


class TestStripPrompt:
    def test_removes_prompt(self) -> None:
        assert strip_prompt("claude-sonnet-4-6:academic") == "claude-sonnet-4-6"

    def test_bare_label_unchanged(self) -> None:
        assert strip_prompt("claude-sonnet-4-6") == "claude-sonnet-4-6"

    def test_only_the_first_colon_splits(self) -> None:
        assert strip_prompt("model:prompt:extra") == "model"


class TestLoadJudgmentRecords:
    def test_missing_directory_returns_empty(self, tmp_path: Path) -> None:
        assert load_judgment_records(tmp_path / "nope") == []

    def test_empty_directory_returns_empty(self, tmp_path: Path) -> None:
        assert load_judgment_records(tmp_path) == []

    def test_annotates_username_and_line_number(self, tmp_path: Path) -> None:
        _write_log(tmp_path, "alice", [_judgment(entry_id="a1"), _judgment(entry_id="a2")])
        records = load_judgment_records(tmp_path)
        assert [(r["username"], r["_lineno"], r["entry_id"]) for r in records] == [
            ("alice", 1, "a1"),
            ("alice", 2, "a2"),
        ]

    def test_sorted_by_timestamp_across_files(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Two users' records interleave by time, not by filename."""
        _write_log(tmp_path, "alice", [_judgment(entry_id="late", timestamp="2026-04-07T09:00:00+00:00")])
        _write_log(tmp_path, "bob", [_judgment(entry_id="early", timestamp="2026-04-07T08:00:00+00:00")])
        _reverse_glob(monkeypatch)
        assert [r["entry_id"] for r in load_judgment_records(tmp_path)] == ["early", "late"]

    def test_same_timestamp_breaks_by_username_before_line(self, tmp_path: Path) -> None:
        """Two people judging in the same instant still replay in one fixed order.

        Username has to outrank the line number: sorting on the line number
        alone would slot bob's only record between alice's two, which is a
        different Elo path.
        """
        stamp = "2026-04-07T06:00:00+00:00"
        _write_log(
            tmp_path,
            "alice",
            [_judgment(entry_id="alice-1", timestamp=stamp), _judgment(entry_id="alice-2", timestamp=stamp)],
        )
        _write_log(tmp_path, "bob", [_judgment(entry_id="bob-1", timestamp=stamp)])
        records = load_judgment_records(tmp_path)
        assert [r["entry_id"] for r in records] == ["alice-1", "alice-2", "bob-1"]

    def test_same_timestamp_within_a_file_keeps_line_order(self, tmp_path: Path) -> None:
        stamp = "2026-04-07T06:00:00+00:00"
        _write_log(
            tmp_path,
            "alice",
            [_judgment(entry_id="first", timestamp=stamp), _judgment(entry_id="second", timestamp=stamp)],
        )
        assert [r["entry_id"] for r in load_judgment_records(tmp_path)] == ["first", "second"]

    def test_missing_timestamp_sorts_first(self, tmp_path: Path) -> None:
        """A record with no timestamp must still load, not raise on the sort key."""
        record = _judgment(entry_id="undated")
        del record["timestamp"]
        _write_log(tmp_path, "alice", [record, _judgment(entry_id="dated")])
        assert [r["entry_id"] for r in load_judgment_records(tmp_path)] == ["undated", "dated"]

    def test_blank_lines_ignored_silently(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """Blank padding is normal in an appended log, so it must not warn.

        Without the explicit skip these reach json.loads and are reported as
        malformed, burying the warnings that matter.
        """
        path = _write_log(tmp_path, "alice", [_judgment()])
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n   \n")
        assert len(load_judgment_records(tmp_path)) == 1
        assert capsys.readouterr().out == ""

    def test_malformed_line_skipped_and_reported(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        path = tmp_path / "alice.jsonl"
        tmp_path.mkdir(exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(json.dumps(_judgment(entry_id="good-1"), ensure_ascii=False) + "\n")
            f.write("{not json\n")
            f.write(json.dumps(_judgment(entry_id="good-2"), ensure_ascii=False) + "\n")

        records = load_judgment_records(tmp_path)
        assert [r["entry_id"] for r in records] == ["good-1", "good-2"]
        # Line numbers count physical lines, so the survivors keep 1 and 3.
        assert [r["_lineno"] for r in records] == [1, 3]
        assert "malformed" in capsys.readouterr().out

    def test_non_object_line_skipped(self, tmp_path: Path) -> None:
        """A bare list or number parses as JSON but has no .get()."""
        path = tmp_path / "alice.jsonl"
        tmp_path.mkdir(exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write("[1, 2]\n")
            f.write("42\n")
            f.write(json.dumps(_judgment(entry_id="good"), ensure_ascii=False) + "\n")
        assert [r["entry_id"] for r in load_judgment_records(tmp_path)] == ["good"]

    def test_undecodable_file_skipped_others_survive(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """A log saved as GBK is one person's loss, not everybody's.

        UnicodeDecodeError subclasses ValueError, so an OSError-only handler
        would let it abort the whole recompute.
        """
        _write_log(tmp_path, "alice", [_judgment(entry_id="good")])
        (tmp_path / "zoe.jsonl").write_bytes(
            json.dumps(_judgment(entry_id="备注"), ensure_ascii=False).encode("gbk") + b"\n"
        )

        records = load_judgment_records(tmp_path)
        assert [r["entry_id"] for r in records] == ["good"]
        assert "unreadable" in capsys.readouterr().out

    def test_unopenable_file_skipped_others_survive(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_log(tmp_path, "alice", [_judgment(entry_id="good")])
        _write_log(tmp_path, "zoe", [_judgment(entry_id="locked")])
        real_open = open

        def fail(path: object, *args: object, **kwargs: object) -> object:
            if str(path).endswith("zoe.jsonl"):
                raise OSError("permission denied")
            return real_open(path, *args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr("builtins.open", fail)
        assert [r["entry_id"] for r in load_judgment_records(tmp_path)] == ["good"]

    def test_byte_order_mark_tolerated(self, tmp_path: Path) -> None:
        """Logs edited on Windows pick up a BOM; utf-8-sig eats it."""
        tmp_path.mkdir(exist_ok=True)
        (tmp_path / "alice.jsonl").write_bytes(
            b"\xef\xbb\xbf" + json.dumps(_judgment(entry_id="good"), ensure_ascii=False).encode("utf-8") + b"\n"
        )
        assert [r["entry_id"] for r in load_judgment_records(tmp_path)] == ["good"]

    def test_non_jsonl_files_ignored(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """Only ``*.jsonl`` is a log, and the stray file must not even be opened.

        It holds a perfectly valid record on purpose: a glob that swept it up
        would load it without warning, so junk content would prove nothing.
        """
        _write_log(tmp_path, "alice", [_judgment(entry_id="good")])
        (tmp_path / "notes.txt").write_text(
            json.dumps(_judgment(entry_id="stray"), ensure_ascii=False) + "\n", encoding="utf-8"
        )
        assert [r["entry_id"] for r in load_judgment_records(tmp_path)] == ["good"]
        assert capsys.readouterr().out == ""


class TestDeterminism:
    """Elo is path dependent, so the replay order is the whole ballgame."""

    def test_order_actually_changes_the_outcome(self) -> None:
        """Guards the tests below: without this, they would prove nothing."""
        first = _judgment(model_a="m1:default", model_b="m2:default", winner="a")
        second = _judgment(model_a="m1:default", model_b="m2:default", winner="b")
        forwards = {r.label: r.rating for r in recompute_elo([first, second])}
        backwards = {r.label: r.rating for r in recompute_elo([second, first])}
        assert forwards != backwards

    def test_write_order_does_not_change_ratings(self, tmp_path: Path) -> None:
        alice = [
            _judgment(model_a="m1:default", model_b="m2:default", winner="a", timestamp="2026-04-07T06:00:00+00:00"),
            _judgment(model_a="m2:default", model_b="m3:default", winner="b", timestamp="2026-04-07T06:02:00+00:00"),
        ]
        bob = [
            _judgment(model_a="m3:default", model_b="m1:default", winner="a", timestamp="2026-04-07T06:01:00+00:00"),
            _judgment(model_a="m1:default", model_b="m2:default", winner="tie", timestamp="2026-04-07T06:03:00+00:00"),
        ]

        one = tmp_path / "one"
        _write_log(one, "alice", alice)
        _write_log(one, "bob", bob)

        two = tmp_path / "two"
        _write_log(two, "bob", bob)
        _write_log(two, "alice", alice)

        assert recompute_elo(load_judgment_records(one)) == recompute_elo(load_judgment_records(two))

    def test_filesystem_order_does_not_change_ratings(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_log(
            tmp_path,
            "alice",
            [_judgment(model_a="m1:default", model_b="m2:default", winner="a", timestamp="2026-04-07T06:00:00+00:00")],
        )
        _write_log(
            tmp_path,
            "bob",
            [_judgment(model_a="m2:default", model_b="m1:default", winner="a", timestamp="2026-04-07T06:01:00+00:00")],
        )
        baseline = recompute_elo(load_judgment_records(tmp_path))
        _reverse_glob(monkeypatch)
        assert recompute_elo(load_judgment_records(tmp_path)) == baseline

    def test_username_tiebreak_fixes_the_replay_order(self, tmp_path: Path) -> None:
        """Same instant throughout, so only the tie-break picks the Elo path.

        alice's two wins for m1 replay before bob's win for m2, which lands
        m1 on 1511.75.  Interleaving the files instead — bob's record between
        alice's two — would give 1514.67 from the very same records.
        """
        stamp = "2026-04-07T06:00:00+00:00"
        _write_log(
            tmp_path,
            "alice",
            [
                _judgment(model_a="m1:x", model_b="m2:x", winner="a", timestamp=stamp),
                _judgment(model_a="m1:x", model_b="m2:x", winner="a", timestamp=stamp),
            ],
        )
        _write_log(tmp_path, "bob", [_judgment(model_a="m1:x", model_b="m2:x", winner="b", timestamp=stamp)])

        ratings = {r.label: r.rating for r in recompute_elo(load_judgment_records(tmp_path))}
        assert ratings["m1:x"] == pytest.approx(1511.75, abs=0.01)
        assert ratings["m2:x"] == pytest.approx(1488.25, abs=0.01)


class TestEligibility:
    def test_consensus_excluded(self) -> None:
        assert elo_eligible(_consensus(), by_prompt=True) is False

    def test_consensus_type_wins_over_pairwise_fields(self) -> None:
        """A consensus record rates one agreed translation, so there is no match.

        The type decides even if the record also carries the pairwise fields,
        which is what keeps the check meaningful rather than incidental to
        ``models`` replacing ``model_a``/``model_b``.
        """
        record = _consensus(model_a="m1:x", model_b="m2:x", winner="a")
        assert elo_eligible(record, by_prompt=True) is False
        assert recompute_elo([record]) == []

    def test_human_reference_as_a_excluded(self) -> None:
        record = _judgment(model_a=HUMAN_REFERENCE, model_b="model-b:default")
        assert elo_eligible(record, by_prompt=False) is False

    def test_human_reference_as_b_excluded(self) -> None:
        record = _judgment(model_a="model-a:default", model_b=HUMAN_REFERENCE)
        assert elo_eligible(record, by_prompt=False) is False

    @pytest.mark.parametrize("winner", ["", "both", "A", None, "skip"])
    def test_unrecognised_winner_excluded(self, winner: object) -> None:
        assert elo_eligible(_judgment(winner=winner), by_prompt=True) is False

    @pytest.mark.parametrize("winner", ["a", "b", "tie", "neither"])
    def test_recognised_winners_included(self, winner: str) -> None:
        assert elo_eligible(_judgment(winner=winner), by_prompt=True) is True

    @pytest.mark.parametrize(
        ("label_a", "label_b"),
        [("model-a", "model-b:default"), ("model-a:default", "model-b")],
    )
    def test_bare_label_on_either_side_excluded_by_prompt(self, label_a: str, label_b: str) -> None:
        """One bare label is enough: the pair cannot be attributed to a prompt."""
        record = _judgment(model_a=label_a, model_b=label_b)
        assert elo_eligible(record, by_prompt=True) is False
        assert elo_eligible(record, by_prompt=False) is True

    def test_both_bare_labels_included_without_prompts(self) -> None:
        record = _judgment(model_a="model-a", model_b="model-b")
        assert elo_eligible(record, by_prompt=True) is False
        assert elo_eligible(record, by_prompt=False) is True

    def test_reference_only_competitor_gets_no_rating(self) -> None:
        """The consequence that matters: the reference is not a competitor.

        A model judged solely against ``human-reference`` has no head-to-head
        record at all, so it must be absent rather than sitting on 1500.
        """
        records = [
            _judgment(model_a="untested:default", model_b=HUMAN_REFERENCE, winner="a"),
            _judgment(model_a=HUMAN_REFERENCE, model_b="untested:default", winner="b"),
            _judgment(model_a="m1:default", model_b="m2:default", winner="a"),
        ]
        labels = [r.label for r in recompute_elo(records)]
        assert labels == ["m1:default", "m2:default"]
        assert HUMAN_REFERENCE not in labels

    def test_ineligible_records_leave_no_ratings(self) -> None:
        records = [_consensus(), _judgment(winner="unclear")]
        assert recompute_elo(records) == []


class TestEloMechanics:
    def test_single_decisive_win(self) -> None:
        ratings = recompute_elo([_judgment(model_a="m1:x", model_b="m2:x", winner="a")])
        assert [(r.label, r.rating) for r in ratings] == [("m1:x", WIN), ("m2:x", LOSS)]

    def test_win_and_loss_are_symmetric(self) -> None:
        ratings = recompute_elo([_judgment(model_a="m1:x", model_b="m2:x", winner="b")])
        winner, loser = ratings[0], ratings[1]
        assert winner.label == "m2:x"
        assert winner.rating - 1500 == pytest.approx(1500 - loser.rating)

    def test_tie_leaves_both_at_default(self) -> None:
        ratings = recompute_elo([_judgment(model_a="m1:x", model_b="m2:x", winner="tie")])
        assert [(r.label, r.rating) for r in ratings] == [("m1:x", 1500.0), ("m2:x", 1500.0)]

    def test_neither_behaves_exactly_like_a_tie(self) -> None:
        """judge.py scores 'neither' as a draw; the recompute must agree."""
        base = {"model_a": "m1:x", "model_b": "m2:x"}
        tie = recompute_elo([_judgment(**base, winner="tie"), _judgment(**base, winner="a")])
        neither = recompute_elo([_judgment(**base, winner="neither"), _judgment(**base, winner="a")])
        assert neither == tie

    def test_tallies_match_the_records(self) -> None:
        records = [
            _judgment(model_a="m1:x", model_b="m2:x", winner="a"),
            _judgment(model_a="m1:x", model_b="m2:x", winner="a"),
            _judgment(model_a="m1:x", model_b="m2:x", winner="b"),
            _judgment(model_a="m2:x", model_b="m1:x", winner="tie"),
            _judgment(model_a="m1:x", model_b="m2:x", winner="neither"),
        ]
        by_label = {r.label: r for r in recompute_elo(records)}
        assert by_label["m1:x"].matches == 5
        assert by_label["m1:x"].wins == 2
        assert by_label["m1:x"].losses == 1
        assert by_label["m1:x"].ties == 2
        assert by_label["m2:x"].wins == 1
        assert by_label["m2:x"].losses == 2
        assert by_label["m2:x"].ties == 2

    def test_neither_counts_as_a_tie_in_the_tally(self) -> None:
        ratings = recompute_elo([_judgment(model_a="m1:x", model_b="m2:x", winner="neither")])
        assert all(r.ties == 1 and r.wins == 0 and r.losses == 0 for r in ratings)

    def test_sorted_by_rating_descending(self) -> None:
        """Rating beats the alphabet: 'zeta' wins, so 'zeta' leads."""
        ratings = recompute_elo([_judgment(model_a="zeta:x", model_b="alpha:x", winner="a")])
        assert [r.label for r in ratings] == ["zeta:x", "alpha:x"]

    def test_equal_ratings_break_by_label(self) -> None:
        records = [
            _judgment(model_a="m-b:x", model_b="m-d:x", winner="tie"),
            _judgment(model_a="m-c:x", model_b="m-a:x", winner="tie"),
        ]
        ratings = recompute_elo(records)
        assert [r.rating for r in ratings] == [1500.0] * 4
        assert [r.label for r in ratings] == ["m-a:x", "m-b:x", "m-c:x", "m-d:x"]

    def test_rating_is_frozen_and_serialisable(self) -> None:
        rating = recompute_elo([_judgment(model_a="m1:x", model_b="m2:x", winner="a")])[0]
        assert rating.as_dict() == {
            "label": "m1:x",
            "rating": 1516.0,
            "matches": 1,
            "wins": 1,
            "losses": 0,
            "ties": 0,
        }
        with pytest.raises(AttributeError):
            rating.rating = 1  # type: ignore[misc]

    def test_as_dict_rounds_to_one_decimal(self) -> None:
        """1516.449 pins the precision from both sides: not 1516.0, not 1516.45."""
        rating = Rating(label="m1:x", rating=1516.449, matches=1, wins=1, losses=0, ties=0)
        assert rating.as_dict()["rating"] == 1516.4


class TestPromptStripping:
    def test_same_model_two_prompts_is_skipped(self) -> None:
        """Stripping prompts collapses both sides onto one competitor.

        Rating a model against itself would move it away from 1500 on noise,
        so the record has to be dropped, not replayed.
        """
        records = [_judgment(model_a="m1:default", model_b="m1:academic", winner="a")]
        assert recompute_elo(records, by_prompt=False) == []
        assert [r.label for r in recompute_elo(records, by_prompt=True)] == ["m1:default", "m1:academic"]

    def test_same_model_skip_does_not_disturb_other_records(self) -> None:
        records = [
            _judgment(model_a="m1:default", model_b="m1:academic", winner="a"),
            _judgment(model_a="m1:academic", model_b="m2:default", winner="a"),
        ]
        ratings = recompute_elo(records, by_prompt=False)
        assert [(r.label, r.rating, r.matches) for r in ratings] == [("m1", WIN, 1), ("m2", LOSS, 1)]

    def test_prompts_collapse_onto_the_model(self) -> None:
        records = [
            _judgment(model_a="m1:default", model_b="m2:default", winner="a"),
            _judgment(model_a="m1:academic", model_b="m2:academic", winner="a"),
        ]
        by_model = recompute_elo(records, by_prompt=False)
        assert [r.label for r in by_model] == ["m1", "m2"]
        assert by_model[0].matches == 2
        assert [r.label for r in recompute_elo(records, by_prompt=True)] == [
            "m1:academic",
            "m1:default",
            "m2:academic",
            "m2:default",
        ]

    def test_bare_labels_only_count_by_model(self) -> None:
        """v0.2-era records name a bare model and cannot be attributed to a prompt."""
        records = [_judgment(model_a="m1", model_b="m2", winner="a", cli_version="0.2.1")]
        assert recompute_elo(records, by_prompt=True) == []
        assert [r.label for r in recompute_elo(records, by_prompt=False)] == ["m1", "m2"]


class TestScoreSummary:
    def test_consensus_credits_every_model_named(self) -> None:
        """One agreed translation, so every model that produced it earns the score."""
        summary = score_summary([_consensus(models=["m1:default", "m2:academic"], accuracy=4, fluency=5)])
        assert summary == {
            "m1:default": {"accuracy": 4.0, "fluency": 5.0, "rated": 1},
            "m2:academic": {"accuracy": 4.0, "fluency": 5.0, "rated": 1},
        }

    def test_consensus_score_is_not_also_counted_pairwise(self) -> None:
        """A consensus record carries one score, so it must be credited once.

        The type is the discriminator: a record that also carried the pairwise
        fields would otherwise have its models scored twice over.
        """
        record = _consensus(
            models=["m1:x"],
            accuracy=4,
            fluency=4,
            model_a="m1:x",
            model_b="m2:x",
            score_a={"accuracy": 1, "fluency": 1},
            score_b={"accuracy": 1, "fluency": 1},
        )
        assert score_summary([record]) == {"m1:x": {"accuracy": 4.0, "fluency": 4.0, "rated": 1}}

    def test_neither_contributes_no_score(self) -> None:
        """None on both sides is 'unscored', not a zero that would drag a mean down."""
        record = _judgment(
            winner="neither",
            score_a={"accuracy": None, "fluency": None},
            score_b={"accuracy": None, "fluency": None},
        )
        assert score_summary([record]) == {}

    def test_neither_does_not_dilute_a_real_mean(self) -> None:
        records = [
            _judgment(model_a="m1:x", model_b="m2:x", score_a={"accuracy": 4, "fluency": 4}),
            _judgment(
                model_a="m1:x",
                model_b="m2:x",
                winner="neither",
                score_a={"accuracy": None, "fluency": None},
                score_b={"accuracy": None, "fluency": None},
            ),
        ]
        assert score_summary(records)["m1:x"] == {"accuracy": 4.0, "fluency": 4.0, "rated": 1}

    def test_mixed_scales_average_after_normalisation(self) -> None:
        """A 10 on the 1-10 scale and a 4 on the 0-5 scale average to 4.5, not 7."""
        records = [
            _judgment(
                cli_version="0.2.1",
                model_a="m1",
                model_b="m2",
                score_a={"accuracy": 10, "fluency": 1},
                score_b={"accuracy": 9, "fluency": 10},
            ),
            _judgment(
                cli_version="0.3.1",
                model_a="m1:academic",
                model_b="m2:default",
                score_a={"accuracy": 4, "fluency": 4},
                score_b={"accuracy": 0, "fluency": 5},
            ),
        ]
        summary = score_summary(records, by_prompt=False)
        assert summary["m1"] == {"accuracy": 4.5, "fluency": 2.0, "rated": 2}
        assert summary["m2"] == {"accuracy": 2.22, "fluency": 5.0, "rated": 2}

    def test_rated_counts_the_contributing_scores(self) -> None:
        records = [
            _judgment(model_a="m1:x", model_b="m2:x"),
            _judgment(model_a="m1:x", model_b="m3:x"),
            _judgment(model_a="m1:x", model_b="m4:x"),
        ]
        assert score_summary(records)["m1:x"]["rated"] == 3
        assert score_summary(records)["m2:x"]["rated"] == 1

    def test_rated_takes_the_larger_of_the_two_dimensions(self) -> None:
        record = _judgment(model_a="m1:x", model_b="m2:x", score_a={"accuracy": None, "fluency": 4})
        assert score_summary([record])["m1:x"] == {"accuracy": None, "fluency": 4.0, "rated": 1}

    def test_human_reference_never_appears(self) -> None:
        """The reference is excluded from ratings, and from scores for the same reason.

        Its label carries no prompt, so ``by_prompt=True`` would drop it either
        way; ``by_prompt=False`` is where the exclusion has to be deliberate.
        """
        record = _judgment(model_a="m1:x", model_b=HUMAN_REFERENCE, score_b={"accuracy": 5, "fluency": 5})
        assert HUMAN_REFERENCE not in score_summary([record], by_prompt=True)
        assert list(score_summary([record], by_prompt=False)) == ["m1"]
        assert score_summary([record])["m1:x"]["accuracy"] == 4.0

    def test_bare_labels_dropped_by_prompt(self) -> None:
        records = [_judgment(model_a="m1", model_b="m2:default", cli_version="0.3.1")]
        assert list(score_summary(records, by_prompt=True)) == ["m2:default"]
        assert sorted(score_summary(records, by_prompt=False)) == ["m1", "m2"]

    def test_consensus_scores_are_normalised_like_any_other(self) -> None:
        """A consensus record carries a version too, so it takes the same rescale.

        Without it a legacy 10 would sit next to a modern 5 in the same mean.
        """
        record = _consensus(models=["m1:x"], accuracy=10, fluency=1, cli_version="0.2.1")
        assert score_summary([record]) == {"m1:x": {"accuracy": 5.0, "fluency": 0.0, "rated": 1}}

    def test_consensus_bare_labels_dropped_by_prompt(self) -> None:
        record = _consensus(models=["m1", "m2:default"])
        assert list(score_summary([record], by_prompt=True)) == ["m2:default"]

    def test_prompts_collapse_onto_the_model(self) -> None:
        records = [
            _judgment(model_a="m1:default", model_b="m2:x", score_a={"accuracy": 5, "fluency": 5}),
            _judgment(model_a="m1:academic", model_b="m2:x", score_a={"accuracy": 3, "fluency": 3}),
        ]
        assert score_summary(records, by_prompt=False)["m1"] == {"accuracy": 4.0, "fluency": 4.0, "rated": 2}

    def test_consensus_credits_a_model_once_even_when_it_names_two_prompts(self) -> None:
        """One translation, rated once — it must not vote twice for one model.

        Live in this repo's log: a consensus over `sonnet:default` and
        `sonnet:academic` collapses to one competitor under by_prompt=False.
        """
        record = _consensus(models=["m1:default", "m1:academic"], accuracy=5, fluency=5)
        summary = score_summary([record], by_prompt=False)
        assert summary["m1"] == {"accuracy": 5.0, "fluency": 5.0, "rated": 1}

    def test_consensus_credits_each_distinct_model(self) -> None:
        record = _consensus(models=["m1:default", "m2:default"], accuracy=4, fluency=4)
        summary = score_summary([record], by_prompt=False)
        assert summary["m1"]["rated"] == 1
        assert summary["m2"]["rated"] == 1

    def test_pairwise_counts_both_sides_of_one_model(self) -> None:
        """Two prompts of one model are two rated outputs, not a duplicate.

        This is the opposite of the consensus case above and the reason the
        de-duplication is not applied blanket across every record type.
        """
        record = _judgment(
            model_a="m1:x", model_b="m1:y",
            score_a={"accuracy": 2, "fluency": 2},
            score_b={"accuracy": 4, "fluency": 4},
        )
        assert score_summary([record], by_prompt=False)["m1"]["rated"] == 2

    def test_scores_count_even_when_elo_skips_the_record(self) -> None:
        """A 'neither' record still carries scores when the judge entered them."""
        record = _judgment(
            model_a="m1:x",
            model_b="m1:y",
            winner="neither",
            score_a={"accuracy": 2, "fluency": 2},
            score_b={"accuracy": 4, "fluency": 4},
        )
        assert recompute_elo([record], by_prompt=False) == []
        assert score_summary([record], by_prompt=False)["m1"] == {"accuracy": 3.0, "fluency": 3.0, "rated": 2}


class TestRobustness:
    def test_missing_model_labels_do_not_crash(self) -> None:
        """No opponent means no match, but the intact side keeps its score."""
        record = _judgment()
        del record["model_a"]
        assert recompute_elo([record]) == []
        assert list(score_summary([record])) == ["model-b:default"]

    @pytest.mark.parametrize("side", ["a", "b"])
    @pytest.mark.parametrize("label", [123, None, ["m1:x"], {"name": "m1:x"}])
    def test_non_string_labels_do_not_crash(self, label: object, side: str) -> None:
        """Either side can be junk, so the type guard has to cover both.

        Guarding only ``model_a`` still crashes on ``":" not in label_b``.
        """
        intact = "model-b:default" if side == "a" else "model-a:default"
        record = _judgment(**{f"model_{side}": label})
        assert recompute_elo([record], by_prompt=True) == []
        assert recompute_elo([record], by_prompt=False) == []
        assert list(score_summary([record])) == [intact]

    @pytest.mark.parametrize("scores", [None, 4, "4", ["accuracy", 4]])
    def test_non_dict_scores_do_not_crash(self, scores: object) -> None:
        record = _judgment(model_a="m1:x", model_b="m2:x", score_a=scores)
        assert list(score_summary([record])) == ["m2:x"]

    def test_missing_scores_do_not_crash(self) -> None:
        record = _judgment(model_a="m1:x", model_b="m2:x")
        del record["score_a"]
        del record["score_b"]
        assert score_summary([record]) == {}
        assert [r.label for r in recompute_elo([record])] == ["m1:x", "m2:x"]

    @pytest.mark.parametrize("models", [None, "m1:x", 7, {"m1:x": 1}])
    def test_consensus_with_a_non_list_models_field_does_not_crash(self, models: object) -> None:
        assert score_summary([_consensus(models=models)]) == {}

    def test_consensus_with_non_string_models_skips_them(self) -> None:
        assert list(score_summary([_consensus(models=["m1:x", 7, None])])) == ["m1:x"]

    def test_missing_cli_version_falls_back_to_the_legacy_scale(self) -> None:
        record = _judgment(model_a="m1:x", model_b="m2:x", score_a={"accuracy": 10, "fluency": 10})
        del record["cli_version"]
        assert score_summary([record])["m1:x"]["accuracy"] == 5.0

    def test_non_string_cli_version_falls_back_to_the_legacy_scale(self) -> None:
        """An explicit JSON null is not a version string and must not raise."""
        record = _judgment(
            model_a="m1:x", model_b="m2:x", cli_version=None, score_a={"accuracy": 10, "fluency": 10}
        )
        assert score_summary([record])["m1:x"]["accuracy"] == 5.0

    def test_empty_records_produce_nothing(self) -> None:
        assert recompute_elo([]) == []
        assert score_summary([]) == {}

    def test_end_to_end_from_disk(self, tmp_path: Path) -> None:
        """The path the dashboard actually takes: directory in, ratings out."""
        _write_log(
            tmp_path,
            "alice",
            [
                _judgment(model_a="m1:academic", model_b="m2:academic", winner="a"),
                _consensus(models=["m1:academic"], accuracy=5, fluency=5),
                _judgment(model_a="m1:academic", model_b=HUMAN_REFERENCE, winner="tie"),
            ],
        )
        records = load_judgment_records(tmp_path)
        assert len(records) == 3
        assert [(r.label, r.rating) for r in recompute_elo(records)] == [("m1:academic", WIN), ("m2:academic", LOSS)]
        assert score_summary(records)["m1:academic"]["rated"] == 3
