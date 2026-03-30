"""Tests for the submit command."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, call, patch

import pytest

from qebench.commands.submit import _has_changes, _run_git, submit


class TestRunGit:
    def test_calls_git_with_args(self) -> None:
        with patch("qebench.commands.submit.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )
            result = _run_git("status", "--short")
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
        responses = {
            "status": subprocess.CompletedProcess(args=[], returncode=0, stdout=" M data/terms/alice.json\n", stderr=""),
            "pull": subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="conflict"),
        }
        with (
            patch("qebench.commands.submit.get_github_username", return_value="alice"),
            patch("qebench.commands.submit.subprocess.run", side_effect=lambda args, **kw: responses.get(args[1], subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr=""))),
        ):
            with pytest.raises(SystemExit):
                submit()

    def test_successful_submit(self) -> None:
        responses = {
            "status": subprocess.CompletedProcess(args=[], returncode=0, stdout=" M data/terms/alice.json\n", stderr=""),
            "pull": subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
            "add": subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
            "diff": subprocess.CompletedProcess(args=[], returncode=0, stdout="data/terms/alice.json\n", stderr=""),
            "commit": subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
            "push": subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
        }
        with (
            patch("qebench.commands.submit.get_github_username", return_value="alice"),
            patch("qebench.commands.submit.subprocess.run", side_effect=lambda args, **kw: responses.get(args[1], subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr=""))),
        ):
            submit()  # Should complete without error
