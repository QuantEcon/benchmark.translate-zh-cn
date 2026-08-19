"""Tests for the stats command."""

from __future__ import annotations

import json

from qebench.commands.stats import _load_leaderboard


class TestBomHandling:
    def test_bom_file_still_counts(self, tmp_path, monkeypatch) -> None:
        """Raised on #33: only export.py had moved to utf-8-sig."""
        monkeypatch.setattr("qebench.commands.stats.XP_DIR", tmp_path)
        (tmp_path / "alice.json").write_text(
            '\ufeff{"total": 150, "actions": {"translate": 150}}', encoding="utf-8"
        )
        (tmp_path / "bob.json").write_text('{"total": 90, "actions": {}}', encoding="utf-8")
        board = _load_leaderboard()
        assert [e["username"] for e in board] == ["alice", "bob"]
        assert board[0]["total"] == 150


class TestLoadLeaderboard:
    def test_empty_directory(self, tmp_path, monkeypatch):
        monkeypatch.setattr("qebench.commands.stats.XP_DIR", tmp_path)
        assert _load_leaderboard() == []

    def test_no_directory(self, tmp_path, monkeypatch):
        monkeypatch.setattr("qebench.commands.stats.XP_DIR", tmp_path / "nonexistent")
        assert _load_leaderboard() == []

    def test_single_user(self, tmp_path, monkeypatch):
        monkeypatch.setattr("qebench.commands.stats.XP_DIR", tmp_path)
        (tmp_path / "alice.json").write_text(
            json.dumps({"total": 50, "actions": {"translate": 30, "add": 20}}),
            encoding="utf-8",
        )
        result = _load_leaderboard()
        assert len(result) == 1
        assert result[0]["username"] == "alice"
        assert result[0]["total"] == 50

    def test_sorted_by_total_desc(self, tmp_path, monkeypatch):
        monkeypatch.setattr("qebench.commands.stats.XP_DIR", tmp_path)
        (tmp_path / "alice.json").write_text(
            json.dumps({"total": 30, "actions": {"translate": 30}}),
            encoding="utf-8",
        )
        (tmp_path / "bob.json").write_text(
            json.dumps({"total": 100, "actions": {"translate": 60, "add": 40}}),
            encoding="utf-8",
        )
        result = _load_leaderboard()
        assert len(result) == 2
        assert result[0]["username"] == "bob"
        assert result[1]["username"] == "alice"

    def test_undecodable_file_does_not_empty_the_leaderboard(self, tmp_path, monkeypatch):
        """A GBK-saved XP file must not cost every other contributor their rank.

        UnicodeDecodeError subclasses ValueError via UnicodeError, so it slips
        past a guard that names only JSONDecodeError and OSError.
        """
        monkeypatch.setattr("qebench.commands.stats.XP_DIR", tmp_path)
        (tmp_path / "alice.json").write_text(
            json.dumps({"total": 30, "actions": {"translate": 30}}),
            encoding="utf-8",
        )
        (tmp_path / "bob.json").write_bytes(
            json.dumps(
                {"total": 100, "actions": {"translate": 60}, "note": "通货膨胀"},
                ensure_ascii=False,
            ).encode("gbk")
        )
        (tmp_path / "carol.json").write_text(
            json.dumps({"total": 70, "actions": {"judge": 70}}),
            encoding="utf-8",
        )

        result = _load_leaderboard()

        # bob is dropped; the readable users survive with their order intact.
        assert [e["username"] for e in result] == ["carol", "alice"]
        assert result[0]["total"] == 70
        assert result[1]["total"] == 30

    def test_undecodable_file_warns_naming_the_file(self, tmp_path, monkeypatch, capsys):
        """Silently vanishing from the leaderboard gives a contributor nothing to debug."""
        monkeypatch.setattr("qebench.commands.stats.XP_DIR", tmp_path)
        (tmp_path / "bob.json").write_bytes(
            json.dumps({"total": 100, "note": "通货膨胀"}, ensure_ascii=False).encode("gbk")
        )

        assert _load_leaderboard() == []

        out = capsys.readouterr().out
        assert "warning" in out
        assert "bob.json" in out

    def test_malformed_json_is_skipped_with_a_warning(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr("qebench.commands.stats.XP_DIR", tmp_path)
        (tmp_path / "alice.json").write_text(
            json.dumps({"total": 30, "actions": {"translate": 30}}),
            encoding="utf-8",
        )
        (tmp_path / "bob.json").write_text("{not json at all", encoding="utf-8")

        result = _load_leaderboard()

        assert [e["username"] for e in result] == ["alice"]
        out = capsys.readouterr().out
        assert "warning" in out
        assert "bob.json" in out

    def test_unreadable_file_is_skipped_with_a_warning(self, tmp_path, monkeypatch, capsys):
        """A file that cannot be opened at all is skipped, not fatal."""
        monkeypatch.setattr("qebench.commands.stats.XP_DIR", tmp_path)
        (tmp_path / "alice.json").write_text(
            json.dumps({"total": 30, "actions": {"translate": 30}}),
            encoding="utf-8",
        )
        (tmp_path / "bob.json").write_text(json.dumps({"total": 100}), encoding="utf-8")

        real_open = open

        def fail_on_bob(path, *args, **kwargs):
            if str(path).endswith("bob.json"):
                raise OSError("permission denied")
            return real_open(path, *args, **kwargs)

        monkeypatch.setattr("builtins.open", fail_on_bob)

        result = _load_leaderboard()

        assert [e["username"] for e in result] == ["alice"]
        out = capsys.readouterr().out
        assert "warning" in out
        assert "bob.json" in out

    def test_non_object_json_is_skipped_with_a_warning(self, tmp_path, monkeypatch, capsys):
        """Valid JSON that is not an object has no .get — it must not raise AttributeError."""
        monkeypatch.setattr("qebench.commands.stats.XP_DIR", tmp_path)
        (tmp_path / "alice.json").write_text(
            json.dumps({"total": 30, "actions": {"translate": 30}}),
            encoding="utf-8",
        )
        (tmp_path / "bob.json").write_text(json.dumps([1, 2, 3]), encoding="utf-8")

        result = _load_leaderboard()

        assert [e["username"] for e in result] == ["alice"]
        out = capsys.readouterr().out
        assert "warning" in out
        assert "bob.json" in out

    def test_non_numeric_total_is_skipped_rather_than_breaking_the_sort(
        self, tmp_path, monkeypatch, capsys
    ):
        """A quoted or null "total" is unsortable — it must not abort the command.

        The isinstance(data, dict) guard only validates the container, so a
        hand-edited '"total": "100"' reached ``entries.sort(key=-e["total"])``
        and raised TypeError there, outside the try block.
        """
        monkeypatch.setattr("qebench.commands.stats.XP_DIR", tmp_path)
        (tmp_path / "alice.json").write_text(
            json.dumps({"total": 30, "actions": {"translate": 30}}),
            encoding="utf-8",
        )
        (tmp_path / "bob.json").write_text(
            json.dumps({"total": "100", "actions": {"translate": 60}}),
            encoding="utf-8",
        )
        (tmp_path / "carol.json").write_text(
            json.dumps({"total": None, "actions": {}}), encoding="utf-8"
        )

        result = _load_leaderboard()

        assert [e["username"] for e in result] == ["alice"]
        out = capsys.readouterr().out
        assert "bob.json" in out
        assert "carol.json" in out

    def test_non_object_actions_keeps_the_user_with_an_empty_breakdown(
        self, tmp_path, monkeypatch, capsys
    ):
        """A malformed "actions" must not crash the leaderboard render.

        stats() calls actions.get("translate", 0) on whatever this returns, so
        a non-dict passed straight through raised AttributeError at render time.
        """
        monkeypatch.setattr("qebench.commands.stats.XP_DIR", tmp_path)
        (tmp_path / "bob.json").write_text(
            json.dumps({"total": 100, "actions": "oops"}), encoding="utf-8"
        )

        result = _load_leaderboard()

        assert [e["username"] for e in result] == ["bob"]
        assert result[0]["total"] == 100
        # stats() does exactly this when rendering the row.
        assert result[0]["actions"].get("translate", 0) == 0
        assert "bob.json" in capsys.readouterr().out
