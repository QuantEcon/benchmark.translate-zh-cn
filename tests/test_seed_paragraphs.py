"""Tests for paragraph curation and the seeder's append mode.

Ids are positional, and translation attempts, judgments and the hand repairs
from #34 are all keyed on them, so the guarantee under test is that appending
never disturbs a committed entry.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "seed_from_lectures.py"
_spec = importlib.util.spec_from_file_location("seed_from_lectures", _SCRIPT_PATH)
assert _spec is not None and _spec.loader is not None
seed = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = seed
_spec.loader.exec_module(seed)


def para(
    en: str,
    *,
    domain: str = "economics",
    directives: bool = False,
    roles: bool = False,
    math: bool = False,
    entry_id: str | None = None,
) -> dict:
    entry = {
        "en": en,
        "zh": "译文",
        "domain": domain,
        "difficulty": "intermediate",
        "contains_math": math,
        "contains_code": False,
        "contains_directives": directives,
        "contains_roles": roles,
        "contains_mixed_fencing": False,
    }
    if entry_id:
        entry["id"] = entry_id
    return entry


class TestIsDuplicate:
    def test_identical_text(self) -> None:
        text = "The determinant equals the product."
        assert seed._is_duplicate(para(text), [para(text)])

    def test_rewrapped_text(self) -> None:
        """para-001 and the same passage re-extracted differ only in line breaks."""
        committed = para(
            "1. Start the current period with prior density $p_t(x)$ for $X_t$.\n"
            "1. Observe the current signal $Y_t = y_t$ and record it.\n"
            "1. Compute the filtering density from $p_t(x)$ and $y_t$ by Bayes rule."
        )
        extracted = para(
            "1. Start the current period with prior density $p_t(x)$ for $X_t$. "
            "1. Observe the current signal $Y_t = y_t$ and record it. "
            "1. Compute the filtering density from $p_t(x)$ and $y_t$ by Bayes rule."
        )

        assert seed._is_duplicate(extracted, [committed])

    def test_a_renumbered_list_item(self) -> None:
        committed = para(
            "1. The determinant of $A$ equals the product of the eigenvalues, taken with multiplicity. "
            "1. The trace of $A$ equals the sum of the eigenvalues, likewise with multiplicity."
        )
        extracted = para(
            "2. The determinant of $A$ equals the product of the eigenvalues, taken with multiplicity. "
            "2. The trace of $A$ equals the sum of the eigenvalues, likewise with multiplicity."
        )

        assert seed._is_duplicate(extracted, [committed])

    def test_unrelated_paragraphs_are_kept(self) -> None:
        assert not seed._is_duplicate(
            para("The trace of $A$ is the sum of its eigenvalues."),
            [para("Agents differ only in their beliefs about the future.")],
        )

    def test_a_much_shorter_paragraph_is_not_a_duplicate(self) -> None:
        """The length gate must not let a substring through as a match."""
        assert not seed._is_duplicate(
            para("The determinant."),
            [para("The determinant of $A$ equals the product of the eigenvalues, taken with multiplicity.")],
        )

    def test_short_text_must_match_exactly(self) -> None:
        """Two short strings clear 0.90 on a one-character difference."""
        assert not seed._is_duplicate(para("Candidate 0."), [para("Candidate 1.")])
        assert seed._is_duplicate(para("Candidate 0."), [para("Candidate 0.")])

    def test_nothing_to_compare_against(self) -> None:
        assert not seed._is_duplicate(para("Anything at all."), [])


class TestCurateParagraphs:
    def test_returns_only_the_new_selections(self) -> None:
        existing = [para("Committed one.", entry_id="para-001")]
        candidates = [
            para(f"Candidate number {i}, of a length that makes it its own passage.", domain=f"d{i}")
            for i in range(5)
        ]

        selected = seed._curate_paragraphs(candidates, target=3, existing=existing)

        assert len(selected) == 2
        assert all(p["en"] != "Committed one." for p in selected)

    def test_a_committed_paragraph_is_never_re_selected(self) -> None:
        passage = (
            "1. Start the current period with prior density $p_t(x)$ for $X_t$.\n"
            "1. Observe the current signal $Y_t = y_t$ and record it for later use."
        )
        other = (
            "Agents differ only in their beliefs about the future, and each type "
            "holds enough resources to purchase the whole of the asset outright."
        )
        existing = [para(passage, entry_id="para-001")]
        candidates = [para(" ".join(passage.split())), para(other)]   # the first is a rewrap

        selected = seed._curate_paragraphs(candidates, target=2, existing=existing)

        assert [p["en"] for p in selected] == [other]

    def test_directive_carrying_candidates_come_first(self) -> None:
        candidates = [
            para("Plain prose, of a reasonable length for comparison.", domain="a"),
            para("Carries {eq}`something` and a directive block here.", domain="a", directives=True),
        ]

        selected = seed._curate_paragraphs(candidates, target=1, existing=[])

        assert selected[0]["contains_directives"]

    def test_one_domain_cannot_take_every_slot(self) -> None:
        candidates = [
            para(f"Economics candidate number {i}, long enough to stand alone.", domain="economics")
            for i in range(10)
        ]
        candidates += [
            para(f"Probability candidate number {i}, long enough to stand alone.", domain="probability")
            for i in range(10)
        ]

        selected = seed._curate_paragraphs(candidates, target=8, existing=[], max_per_domain=3)

        counts = {d: sum(1 for p in selected if p["domain"] == d) for d in ("economics", "probability")}
        assert counts["economics"] <= 3
        assert counts["probability"] <= 3

    def test_a_domain_already_covered_waits_its_turn(self) -> None:
        existing = [
            para(f"Committed passage {i}, long enough to stand alone.", domain="economics", entry_id=f"para-00{i}")
            for i in range(3)
        ]
        candidates = [para("An economics candidate of some length.", domain="economics")]
        candidates += [para("A probability candidate of some length.", domain="probability")]

        selected = seed._curate_paragraphs(candidates, target=4, existing=existing)

        assert selected[0]["domain"] == "probability"

    def test_it_stops_when_candidates_run_out(self) -> None:
        selected = seed._curate_paragraphs([para("Only one.")], target=30, existing=[])

        assert len(selected) == 1

    def test_an_already_full_set_selects_nothing(self) -> None:
        existing = [
            para(f"Committed passage {i}, long enough to stand alone.", entry_id=f"para-{i:03d}")
            for i in range(30)
        ]

        assert seed._curate_paragraphs([para("A fresh candidate.")], target=30, existing=existing) == []


class TestNextId:
    def test_continues_past_the_highest_committed_id(self) -> None:
        assert seed._next_id([{"id": "para-001"}, {"id": "para-017"}], "para") == 18

    def test_an_empty_set_starts_at_one(self) -> None:
        assert seed._next_id([], "para") == 1

    def test_gaps_do_not_reuse_an_id(self) -> None:
        """Reusing a deleted id would attach old judgments to new text."""
        assert seed._next_id([{"id": "para-001"}, {"id": "para-009"}], "para") == 10

    def test_an_unparseable_id_is_skipped(self) -> None:
        assert seed._next_id([{"id": "para-abc"}, {"id": "para-004"}], "para") == 5


class TestLoadExisting:
    def test_missing_file_reads_as_empty(self, tmp_path: Path) -> None:
        assert seed._load_existing(tmp_path / "nope.json") == []

    def test_reads_a_committed_file(self, tmp_path: Path) -> None:
        path = tmp_path / "seed.json"
        path.write_text(json.dumps([para("One.", entry_id="para-001")]), encoding="utf-8")

        assert [e["id"] for e in seed._load_existing(path)] == ["para-001"]


class TestCommittedData:
    """The shipped file is the thing the ids actually protect."""

    def test_paragraph_ids_are_unique_and_contiguous(self) -> None:
        path = Path(__file__).resolve().parents[1] / "data" / "paragraphs" / "_seed_lectures.json"
        entries = json.loads(path.read_text(encoding="utf-8"))

        ids = [e["id"] for e in entries]
        assert ids == sorted(set(ids))
        assert ids == [f"para-{i:03d}" for i in range(1, len(entries) + 1)]

    def test_no_two_paragraphs_are_the_same_passage(self) -> None:
        path = Path(__file__).resolve().parents[1] / "data" / "paragraphs" / "_seed_lectures.json"
        entries = json.loads(path.read_text(encoding="utf-8"))

        for i, entry in enumerate(entries):
            assert not seed._is_duplicate(entry, entries[:i]), entry["id"]
