"""Tests for GitHub identity utilities."""

from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

from qebench.utils.github import get_github_username


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    """Clear the lru_cache between tests."""
    get_github_username.cache_clear()


class TestGetGithubUsername:
    def test_returns_username(self) -> None:
        mock_result = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="testuser\n", stderr=""
        )
        with patch("qebench.utils.github.subprocess.run", return_value=mock_result):
            assert get_github_username() == "testuser"

    def test_caches_result(self) -> None:
        mock_result = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="testuser\n", stderr=""
        )
        with patch("qebench.utils.github.subprocess.run", return_value=mock_result) as mock_run:
            get_github_username()
            get_github_username()
            assert mock_run.call_count == 1

    def test_gh_not_installed(self) -> None:
        with patch("qebench.utils.github.subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(SystemExit):
                get_github_username()

    def test_gh_not_authenticated(self) -> None:
        mock_result = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="not logged in"
        )
        with patch("qebench.utils.github.subprocess.run", return_value=mock_result):
            with pytest.raises(SystemExit):
                get_github_username()

    def test_empty_username(self) -> None:
        mock_result = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )
        with patch("qebench.utils.github.subprocess.run", return_value=mock_result):
            with pytest.raises(SystemExit):
                get_github_username()

    def test_strips_whitespace(self) -> None:
        mock_result = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="  alice  \n", stderr=""
        )
        with patch("qebench.utils.github.subprocess.run", return_value=mock_result):
            assert get_github_username() == "alice"
