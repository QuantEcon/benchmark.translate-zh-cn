"""Tests for the submit command."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from qebench.commands.submit import _has_changes, _run_git, submit


class TestRunGit:
    def test_calls_git_with_args(self) -> None:
        with patch("qebench.commands.submit.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )
            _run_git("status", "--short")
            mock_run.assert_called_once_with(
                ["git", "status", "--short"],
                capture_output=True,
                text=True,
                timeout=30,
            )


class TestHasChanges:
    def test_no_changes(self) -> None:
        mock_result = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )
        with patch("qebench.commands.submit.subprocess.run", return_value=mock_result):
            assert _has_changes() is False

    def test_has_changes(self) -> None:
        mock_result = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=" M data/terms/alice.json\n", stderr=""
        )
        with patch("qebench.commands.submit.subprocess.run", return_value=mock_result):
            assert _has_changes() is True


class TestSubmit:
    def _mock_run(self, responses: dict[str, subprocess.CompletedProcess]) -> MagicMock:
        """Create a mock that returns different results by first git arg."""
        def side_effect(args, **kwargs):
            # Match by the git subcommand (args[1])
            key = args[1] if len(args) > 1 else ""
            return responses.get(key, subprocess.CompletedProcess(
                args=args, returncode=0, stdout="", stderr=""
            ))
        mock = MagicMock(side_effect=side_effect)
        return mock

    def test_no_changes_exits_early(self) -> None:
        no_changes = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )
        with (
            patch("qebench.commands.submit.get_github_username", return_value="alice"),
            patch("qebench.commands.submit.subprocess.run", return_value=no_changes),
        ):
            submit()  # Should return without error

    def test_pull_failure_exits(self) -> None:
        cp = subprocess.CompletedProcess
        responses = {
            "status": cp(args=[], returncode=0, stdout=" M data/terms/alice.json\n", stderr=""),
            "pull": cp(args=[], returncode=1, stdout="", stderr="conflict"),
        }
        mock = self._mock_run(responses)
        with (
            patch("qebench.commands.submit.get_github_username", return_value="alice"),
            patch("qebench.commands.submit.subprocess.run", side_effect=mock.side_effect),
        ):
            with pytest.raises(SystemExit):
                submit()

    def test_successful_submit(self) -> None:
        cp = subprocess.CompletedProcess
        responses = {
            "status": cp(args=[], returncode=0, stdout=" M data/terms/alice.json\n", stderr=""),
            "pull": cp(args=[], returncode=0, stdout="", stderr=""),
            "add": cp(args=[], returncode=0, stdout="", stderr=""),
            "diff": cp(args=[], returncode=0, stdout="data/terms/alice.json\n", stderr=""),
            "commit": cp(args=[], returncode=0, stdout="", stderr=""),
            "push": cp(args=[], returncode=0, stdout="", stderr=""),
        }
        mock = self._mock_run(responses)
        with (
            patch("qebench.commands.submit.get_github_username", return_value="alice"),
            patch("qebench.commands.submit.subprocess.run", side_effect=mock.side_effect),
        ):
            submit()  # Should complete without error

    def test_push_failure_exits(self) -> None:
        """If push fails, submit exits and tells RA to try again."""
        cp = subprocess.CompletedProcess
        responses = {
            "status": cp(args=[], returncode=0, stdout=" M data/terms/alice.json\n", stderr=""),
            "pull": cp(args=[], returncode=0, stdout="", stderr=""),
            "add": cp(args=[], returncode=0, stdout="", stderr=""),
            "diff": cp(args=[], returncode=0, stdout="data/terms/alice.json\n", stderr=""),
            "commit": cp(args=[], returncode=0, stdout="", stderr=""),
            "push": cp(args=[], returncode=1, stdout="", stderr="rejected"),
        }
        mock = self._mock_run(responses)
        with (
            patch("qebench.commands.submit.get_github_username", return_value="alice"),
            patch("qebench.commands.submit.subprocess.run", side_effect=mock.side_effect),
        ):
            with pytest.raises(SystemExit):
                submit()

    def test_stages_before_pull_with_autostash(self) -> None:
        """Regression: git add before pull --rebase --autostash (issue #8)."""
        cp = subprocess.CompletedProcess
        call_log: list[tuple] = []  # (subcmd, full_args)

        def track_calls(args, **kwargs):
            cmd = args[1] if len(args) > 1 else ""
            call_log.append((cmd, list(args)))
            responses = {
                "status": cp(args=[], returncode=0, stdout=" M results/xp/alice.json\n", stderr=""),
                "pull": cp(args=[], returncode=0, stdout="", stderr=""),
                "add": cp(args=[], returncode=0, stdout="", stderr=""),
                "diff": cp(args=[], returncode=0, stdout="results/xp/alice.json\n", stderr=""),
                "commit": cp(args=[], returncode=0, stdout="", stderr=""),
                "push": cp(args=[], returncode=0, stdout="", stderr=""),
            }
            return responses.get(cmd, cp(args=args, returncode=0, stdout="", stderr=""))

        with (
            patch("qebench.commands.submit.get_github_username", return_value="alice"),
            patch("qebench.commands.submit.subprocess.run", side_effect=track_calls),
        ):
            submit()

        subcmds = [c[0] for c in call_log]

        # 'add' must appear before 'pull' in the call sequence
        add_idx = subcmds.index("add")
        pull_idx = subcmds.index("pull")
        assert add_idx < pull_idx, f"git add ({add_idx}) must come before git pull ({pull_idx}): {subcmds}"

        # pull must include --autostash to handle staged-but-uncommitted changes
        pull_args = next(args for cmd, args in call_log if cmd == "pull")
        assert "--autostash" in pull_args, f"pull should use --autostash: {pull_args}"
