"""Tests for the update command."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from qebench.commands.update import update


class TestUpdate:
    def _mock_run(self, responses: dict[str, subprocess.CompletedProcess]) -> MagicMock:
        """Create a mock that returns different results by first command arg."""
        def side_effect(args, **kwargs):
            # Match by executable name (git or uv)
            key = args[0] if args else ""
            return responses.get(key, subprocess.CompletedProcess(
                args=args, returncode=0, stdout="", stderr=""
            ))
        return MagicMock(side_effect=side_effect)

    def test_successful_update_already_current(self) -> None:
        responses = {
            "git": subprocess.CompletedProcess(
                args=[], returncode=0, stdout="Already up to date.\n", stderr=""
            ),
            "uv": subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            ),
        }
        with patch("qebench.commands.update.subprocess.run", side_effect=lambda args, **kw: responses.get(args[0])):
            update()  # Should complete without error

    def test_successful_update_with_new_commits(self) -> None:
        responses = {
            "git": subprocess.CompletedProcess(
                args=[], returncode=0, stdout="Updating abc1234..def5678\n", stderr=""
            ),
            "uv": subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            ),
        }
        with patch("qebench.commands.update.subprocess.run", side_effect=lambda args, **kw: responses.get(args[0])):
            update()  # Should complete without error

    def test_pull_failure_exits(self) -> None:
        responses = {
            "git": subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr="error: cannot pull with rebase"
            ),
        }
        with patch("qebench.commands.update.subprocess.run", side_effect=lambda args, **kw: responses.get(args[0])):
            with pytest.raises(SystemExit):
                update()

    def test_uv_sync_failure_exits(self) -> None:
        responses = {
            "git": subprocess.CompletedProcess(
                args=[], returncode=0, stdout="Already up to date.\n", stderr=""
            ),
            "uv": subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr="error: could not resolve"
            ),
        }
        with patch("qebench.commands.update.subprocess.run", side_effect=lambda args, **kw: responses.get(args[0])):
            with pytest.raises(SystemExit):
                update()
