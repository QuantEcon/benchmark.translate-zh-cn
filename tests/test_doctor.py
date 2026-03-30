"""Tests for the doctor command."""

from __future__ import annotations

import subprocess
from unittest.mock import patch

from qebench.commands.doctor import _check, _cmd_ok


class TestCheck:
    def test_passing_check(self, capsys) -> None:
        assert _check("Test", True) is True

    def test_failing_check(self, capsys) -> None:
        assert _check("Test", False, "fix it") is False


class TestCmdOk:
    def test_success(self) -> None:
        mock_result = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="hello\n", stderr=""
        )
        with patch("qebench.commands.doctor.subprocess.run", return_value=mock_result):
            ok, output = _cmd_ok("echo", "hello")
        assert ok is True
        assert output == "hello"

    def test_failure(self) -> None:
        mock_result = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="error"
        )
        with patch("qebench.commands.doctor.subprocess.run", return_value=mock_result):
            ok, output = _cmd_ok("false")
        assert ok is False

    def test_command_not_found(self) -> None:
        with patch("qebench.commands.doctor.subprocess.run", side_effect=FileNotFoundError):
            ok, output = _cmd_ok("nonexistent")
        assert ok is False
        assert output == ""

    def test_timeout(self) -> None:
        with patch(
            "qebench.commands.doctor.subprocess.run",
            side_effect=subprocess.TimeoutExpired("cmd", 10),
        ):
            ok, output = _cmd_ok("slow")
        assert ok is False
        assert output == ""
