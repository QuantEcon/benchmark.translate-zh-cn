"""Tests for the update command with context enrichment."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from qebench.commands.update import _enrich_term_contexts, _sync_lecture_repos, update


class TestUpdate:
    def _mock_run(self, responses: dict[str, subprocess.CompletedProcess]) -> MagicMock:
        """Create a mock that returns different results by first command arg."""
        def side_effect(args, **kwargs):
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
        with (
            patch("qebench.commands.update.subprocess.run", side_effect=lambda args, **kw: responses.get(args[0])),
            patch("qebench.commands.update._sync_lecture_repos", return_value=[]),
            patch("qebench.commands.update._enrich_term_contexts", return_value=0),
        ):
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
        with (
            patch("qebench.commands.update.subprocess.run", side_effect=lambda args, **kw: responses.get(args[0])),
            patch("qebench.commands.update._sync_lecture_repos", return_value=[]),
            patch("qebench.commands.update._enrich_term_contexts", return_value=0),
        ):
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

    def test_enrichment_runs_after_sync(self) -> None:
        """Enrichment is called when lecture dirs are available."""
        responses = {
            "git": subprocess.CompletedProcess(
                args=[], returncode=0, stdout="Already up to date.\n", stderr=""
            ),
            "uv": subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            ),
        }
        mock_enrich = MagicMock(return_value=5)
        with (
            patch("qebench.commands.update.subprocess.run", side_effect=lambda args, **kw: responses.get(args[0])),
            patch("qebench.commands.update._sync_lecture_repos", return_value=[Path("/fake")]),
            patch("qebench.commands.update._enrich_term_contexts", mock_enrich),
        ):
            update()
        mock_enrich.assert_called_once_with([Path("/fake")])


class TestSyncLectureRepos:
    def test_clones_missing_repos(self, tmp_path: Path) -> None:
        """When repo dir doesn't exist, git clone is called."""
        calls: list[list[str]] = []

        def fake_run(args, **kwargs):
            calls.append(args)
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

        with (
            patch("qebench.commands.update.CACHE_DIR", tmp_path),
            patch("qebench.commands.update.subprocess.run", side_effect=fake_run),
            patch("qebench.commands.update.LECTURE_REPOS", ["test-repo"]),
        ):
            dirs = _sync_lecture_repos()

        # Should have called git clone
        clone_calls = [c for c in calls if "clone" in c]
        assert len(clone_calls) == 1
        assert str(tmp_path / "test-repo") in clone_calls[0]
        assert dirs == [tmp_path / "test-repo"]

    def test_pulls_existing_repos(self, tmp_path: Path) -> None:
        """When repo dir exists, git pull is called."""
        repo_dir = tmp_path / "test-repo"
        repo_dir.mkdir()
        calls: list[list[str]] = []

        def fake_run(args, **kwargs):
            calls.append(args)
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

        with (
            patch("qebench.commands.update.CACHE_DIR", tmp_path),
            patch("qebench.commands.update.subprocess.run", side_effect=fake_run),
            patch("qebench.commands.update.LECTURE_REPOS", ["test-repo"]),
        ):
            dirs = _sync_lecture_repos()

        pull_calls = [c for c in calls if "pull" in c]
        assert len(pull_calls) == 1
        assert dirs == [repo_dir]

    def test_clone_failure_skips_repo(self, tmp_path: Path) -> None:
        """Failed clone should skip the repo but continue."""
        def fake_run(args, **kwargs):
            if "clone" in args:
                return subprocess.CompletedProcess(args=args, returncode=1, stdout="", stderr="fatal")
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

        with (
            patch("qebench.commands.update.CACHE_DIR", tmp_path),
            patch("qebench.commands.update.subprocess.run", side_effect=fake_run),
            patch("qebench.commands.update.LECTURE_REPOS", ["bad-repo"]),
        ):
            dirs = _sync_lecture_repos()

        assert dirs == []

    def test_pull_failure_keeps_cached(self, tmp_path: Path) -> None:
        """Failed pull should still include the repo dir (use cached)."""
        repo_dir = tmp_path / "test-repo"
        repo_dir.mkdir()

        def fake_run(args, **kwargs):
            if "pull" in args:
                return subprocess.CompletedProcess(args=args, returncode=1, stdout="", stderr="error")
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

        with (
            patch("qebench.commands.update.CACHE_DIR", tmp_path),
            patch("qebench.commands.update.subprocess.run", side_effect=fake_run),
            patch("qebench.commands.update.LECTURE_REPOS", ["test-repo"]),
        ):
            dirs = _sync_lecture_repos()

        assert dirs == [repo_dir]


class TestEnrichTermContexts:
    def test_enriches_and_writes_back(self, tmp_path: Path) -> None:
        """Enriched terms should be written back to their JSON files."""
        # Set up a terms directory with one seed file
        terms_dir = tmp_path / "data" / "terms"
        terms_dir.mkdir(parents=True)

        terms_data = [
            {
                "id": "term-001",
                "en": "dynamic programming",
                "zh": "动态规划",
                "domain": "optimization",
                "difficulty": "intermediate",
                "alternatives": [],
                "source": "test",
            }
        ]
        seed_file = terms_dir / "_seed_test.json"
        seed_file.write_text(json.dumps(terms_data, ensure_ascii=False))

        # Create lecture content with matching term
        lecture_dir = tmp_path / "lectures"
        lecture_dir.mkdir()
        (lecture_dir / "intro.md").write_text(
            "Dynamic programming is a method for solving complex problems."
        )

        with (
            patch("qebench.commands.update.DATA_DIR", tmp_path / "data"),
            patch("qebench.commands.update.load_terms") as mock_load,
        ):
            from qebench.models import Term
            mock_load.return_value = [Term.model_validate(terms_data[0])]
            enriched = _enrich_term_contexts([lecture_dir])

        assert enriched == 1

        # Verify the file was written with contexts
        with open(seed_file) as f:
            written = json.load(f)
        assert len(written) == 1
        assert "contexts" in written[0]
        assert len(written[0]["contexts"]) >= 1

    def test_no_terms_returns_zero(self) -> None:
        with patch("qebench.commands.update.load_terms", return_value=[]):
            assert _enrich_term_contexts([]) == 0
