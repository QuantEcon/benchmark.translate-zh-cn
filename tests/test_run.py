"""Tests for the run command."""

from __future__ import annotations

import json

import pytest
import typer

from qebench.commands.run import _get_provider, _save_results
from qebench.providers.base import TranslationResult


class TestGetProvider:
    def test_unknown_provider_raises(self) -> None:
        with pytest.raises(typer.BadParameter, match="Unknown provider"):
            _get_provider("nonexistent")

    def test_claude_import_error(self, monkeypatch) -> None:
        """If anthropic is not installed, should raise ImportError."""
        import importlib

        def mock_import(name, *args, **kwargs):
            if name == "anthropic":
                raise ImportError("no anthropic")
            return importlib.__import__(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", mock_import)
        with pytest.raises(ImportError, match="anthropic"):
            _get_provider("claude")

    def test_openai_import_error(self, monkeypatch) -> None:
        """If openai is not installed, should raise ImportError."""
        import importlib

        def mock_import(name, *args, **kwargs):
            if name == "openai":
                raise ImportError("no openai")
            return importlib.__import__(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", mock_import)
        with pytest.raises(ImportError, match="openai"):
            _get_provider("openai")


class TestSaveResults:
    def test_saves_jsonl(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr("qebench.commands.run.MODEL_OUTPUTS_DIR", tmp_path)
        results = [
            TranslationResult(
                entry_id="term-001",
                source_text="inflation",
                translated_text="通货膨胀",
                model="test-model",
                provider="test",
                prompt_template="default",
                input_tokens=50,
                output_tokens=10,
                cost_usd=0.0001,
                latency_ms=200.0,
            ),
            TranslationResult(
                entry_id="term-002",
                source_text="GDP",
                translated_text="国内生产总值",
                model="test-model",
                provider="test",
                prompt_template="default",
                input_tokens=40,
                output_tokens=15,
                cost_usd=0.00015,
                latency_ms=180.0,
            ),
        ]
        entry_meta = {
            "term-001": {"domain": "economics", "difficulty": "intermediate"},
            "term-002": {"domain": "economics", "difficulty": "beginner"},
        }
        path = _save_results(
            results, "test-run-123", prompt_name="default",
            entry_type="terms", entry_meta=entry_meta,
        )
        assert path.exists()
        lines = [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        assert len(lines) == 2
        assert lines[0]["entry_id"] == "term-001"
        assert lines[0]["translated_text"] == "通货膨胀"
        assert lines[0]["prompt_template"] == "default"
        assert lines[0]["entry_type"] == "terms"
        assert lines[0]["domain"] == "economics"
        assert lines[0]["difficulty"] == "intermediate"
        assert lines[1]["entry_id"] == "term-002"

    def test_appends_to_existing(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr("qebench.commands.run.MODEL_OUTPUTS_DIR", tmp_path)
        result = TranslationResult(
            entry_id="term-001",
            source_text="x",
            translated_text="y",
            model="m",
            provider="p",
            prompt_template="t",
        )
        meta = {"term-001": {"domain": "d", "difficulty": "beginner"}}
        _save_results([result], "run-1", prompt_name="t", entry_type="terms", entry_meta=meta)
        _save_results([result], "run-1", prompt_name="t", entry_type="terms", entry_meta=meta)
        path = tmp_path / "run-1.jsonl"
        lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        assert len(lines) == 2

    def test_creates_directory(self, tmp_path, monkeypatch) -> None:
        out_dir = tmp_path / "nested" / "output"
        monkeypatch.setattr("qebench.commands.run.MODEL_OUTPUTS_DIR", out_dir)
        result = TranslationResult(
            entry_id="term-001",
            source_text="x",
            translated_text="y",
            model="m",
            provider="p",
            prompt_template="t",
        )
        meta = {"term-001": {"domain": "d", "difficulty": "beginner"}}
        path = _save_results([result], "run-1", prompt_name="t", entry_type="terms", entry_meta=meta)
        assert path.exists()
