"""Tests for XP scoring module."""

from __future__ import annotations

import json

import pytest

from qebench.scoring.xp import (
    XP_ADD,
    XP_JUDGE,
    XP_TRANSLATE,
    award_xp,
    load_xp,
    load_xp_details,
)


@pytest.fixture()
def xp_dir(tmp_path, monkeypatch):
    """Override XP_DIR to use a temp directory."""
    import qebench.scoring.xp as xp_mod

    monkeypatch.setattr(xp_mod, "XP_DIR", tmp_path)
    return tmp_path


class TestXPValues:
    def test_translate_xp_is_10(self):
        assert XP_TRANSLATE == 10

    def test_add_xp_is_15(self):
        assert XP_ADD == 15

    def test_judge_xp_is_5(self):
        assert XP_JUDGE == 5


class TestLoadXP:
    def test_returns_zero_for_new_user(self, xp_dir):
        assert load_xp("newuser") == 0

    def test_returns_total_from_file(self, xp_dir):
        path = xp_dir / "alice.json"
        path.write_text(json.dumps({"total": 150, "actions": {"translate": 100, "add": 50}}))
        assert load_xp("alice") == 150


class TestAwardXP:
    def test_awards_translate_xp(self, xp_dir):
        earned = award_xp("bob", "translate", 3)
        assert earned == 30  # 10 * 3
        assert load_xp("bob") == 30

    def test_awards_add_xp(self, xp_dir):
        earned = award_xp("bob", "add", 2)
        assert earned == 30  # 15 * 2

    def test_awards_judge_xp(self, xp_dir):
        earned = award_xp("bob", "judge", 4)
        assert earned == 20  # 5 * 4

    def test_accumulates_across_calls(self, xp_dir):
        award_xp("carol", "translate", 5)
        award_xp("carol", "add", 1)
        assert load_xp("carol") == 65  # 50 + 15

    def test_unknown_action_awards_zero(self, xp_dir):
        earned = award_xp("dave", "unknown", 10)
        assert earned == 0
        assert load_xp("dave") == 0

    def test_creates_directory_if_missing(self, xp_dir, tmp_path):
        import qebench.scoring.xp as xp_mod

        nested = tmp_path / "deep" / "nested"
        xp_mod.XP_DIR = nested
        award_xp("eve", "translate", 1)
        assert (nested / "eve.json").exists()


class TestCopilotFollowUps:
    """Cases raised on #33: bool totals and BOM'd files."""

    def test_boolean_total_is_rejected_not_counted_as_one(self, tmp_path, monkeypatch) -> None:
        """bool subclasses int, so `true` would otherwise be accepted as 1 XP.

        stats.py rejects it and both read the same files, so they must agree.
        """
        monkeypatch.setattr("qebench.scoring.xp.XP_DIR", tmp_path)
        (tmp_path / "alice.json").write_text('{"total": true, "actions": {}}', encoding="utf-8")
        assert load_xp("alice") == 0

    def test_boolean_total_does_not_clobber_the_file(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr("qebench.scoring.xp.XP_DIR", tmp_path)
        path = tmp_path / "alice.json"
        original = '{"total": true, "actions": {}}'
        path.write_text(original, encoding="utf-8")
        assert award_xp("alice", "translate", 1) == 0
        assert path.read_text(encoding="utf-8") == original

    def test_bom_file_is_read_not_discarded(self, tmp_path, monkeypatch) -> None:
        """A Windows BOM is recoverable; export.py already reads utf-8-sig."""
        monkeypatch.setattr("qebench.scoring.xp.XP_DIR", tmp_path)
        (tmp_path / "alice.json").write_text(
            '\ufeff{"total": 150, "actions": {"translate": 150}}', encoding="utf-8"
        )
        assert load_xp("alice") == 150


class TestCorruptXPFiles:
    """Contributors hand-edit these files, so unreadable ones must not be fatal."""

    def test_load_xp_returns_zero_for_undecodable_file(self, xp_dir):
        """A file saved as GBK rather than UTF-8 is skipped, not fatal.

        UnicodeDecodeError subclasses ValueError, so neither an OSError nor a
        JSONDecodeError handler would catch it.
        """
        (xp_dir / "alice.json").write_bytes(
            json.dumps({"total": 150, "actions": {}, "note": "通货膨胀"}, ensure_ascii=False).encode("gbk")
        )
        assert load_xp("alice") == 0

    def test_load_xp_returns_zero_for_truncated_file(self, xp_dir):
        (xp_dir / "alice.json").write_text('{"total": 150, "actions": {"translate": 1')
        assert load_xp("alice") == 0

    def test_load_xp_returns_zero_for_non_object_json(self, xp_dir):
        (xp_dir / "alice.json").write_text("[150]")
        assert load_xp("alice") == 0

    def test_load_xp_returns_zero_for_unreadable_file(self, xp_dir, monkeypatch):
        """A file that cannot be opened at all is skipped, not fatal."""
        (xp_dir / "alice.json").write_text(json.dumps({"total": 150, "actions": {}}))

        def fail(path, *args, **kwargs):
            raise OSError("permission denied")

        monkeypatch.setattr("builtins.open", fail)
        assert load_xp("alice") == 0

    def test_load_xp_details_falls_back_for_undecodable_file(self, xp_dir):
        (xp_dir / "alice.json").write_bytes(
            json.dumps({"total": 150, "actions": {}, "note": "通货膨胀"}, ensure_ascii=False).encode("gbk")
        )
        assert load_xp_details("alice") == {"total": 0, "actions": {}}

    def test_load_xp_details_falls_back_for_non_object_json(self, xp_dir):
        (xp_dir / "alice.json").write_text('"150"')
        assert load_xp_details("alice") == {"total": 0, "actions": {}}

    def test_award_xp_does_not_overwrite_undecodable_file(self, xp_dir):
        """The XP file is the only record of a total — never reset it to zero.

        Awarding nothing is recoverable once the file is repaired; writing a
        fresh total over the contributor's own is not.
        """
        path = xp_dir / "grace.json"
        corrupt = json.dumps(
            {"total": 150, "actions": {"translate": 150}, "note": "通货膨胀"}, ensure_ascii=False
        ).encode("gbk")
        path.write_bytes(corrupt)

        earned = award_xp("grace", "translate", 3)

        assert earned == 0
        assert path.read_bytes() == corrupt

    def test_award_xp_does_not_overwrite_truncated_file(self, xp_dir):
        path = xp_dir / "grace.json"
        corrupt = '{"total": 150, "actions": {"translate": 1'
        path.write_text(corrupt)

        earned = award_xp("grace", "translate", 3)

        assert earned == 0
        assert path.read_text() == corrupt

    def test_award_xp_does_not_overwrite_non_object_json(self, xp_dir):
        path = xp_dir / "grace.json"
        path.write_text("[150]")

        earned = award_xp("grace", "judge", 1)

        assert earned == 0
        assert path.read_text() == "[150]"

    def test_award_xp_does_not_crash_on_null_total(self, xp_dir):
        """{"total": null} parses as an object but breaks award_xp's arithmetic."""
        path = xp_dir / "grace.json"
        corrupt = '{"total": null, "actions": {}}'
        path.write_text(corrupt)

        earned = award_xp("grace", "translate", 3)

        assert earned == 0
        assert path.read_text() == corrupt

    def test_award_xp_does_not_crash_on_null_actions(self, xp_dir):
        """{"actions": null} parses as an object but breaks actions.get."""
        path = xp_dir / "grace.json"
        corrupt = '{"total": 5, "actions": null}'
        path.write_text(corrupt)

        earned = award_xp("grace", "translate", 3)

        assert earned == 0
        assert path.read_text() == corrupt

    def test_load_xp_returns_int_for_string_total(self, xp_dir):
        """load_xp is annotated -> int; a hand-edited string total must not leak out."""
        (xp_dir / "alice.json").write_text('{"total": "150", "actions": {}}')
        assert load_xp("alice") == 0

    def test_award_xp_preserves_non_ascii_fields_unescaped(self, xp_dir):
        """Rewriting must not re-escape Chinese text in a committed XP file."""
        path = xp_dir / "grace.json"
        path.write_text(
            json.dumps({"total": 10, "actions": {"translate": 10}, "note": "通货膨胀"},
                       ensure_ascii=False),
            encoding="utf-8",
        )

        assert award_xp("grace", "translate", 1) == 10
        assert "通货膨胀" in path.read_text(encoding="utf-8")
        assert "\\u" not in path.read_text(encoding="utf-8")


class TestLoadXPDetails:
    def test_returns_empty_for_new_user(self, xp_dir):
        details = load_xp_details("nobody")
        assert details == {"total": 0, "actions": {}}

    def test_returns_breakdown(self, xp_dir):
        award_xp("frank", "translate", 2)
        award_xp("frank", "judge", 3)
        details = load_xp_details("frank")
        assert details["total"] == 35  # 20 + 15
        assert details["actions"]["translate"] == 20
        assert details["actions"]["judge"] == 15
