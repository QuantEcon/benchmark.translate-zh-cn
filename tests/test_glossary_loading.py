"""Tests for glossary loading from config (URL and local path)."""

from __future__ import annotations

import json

import pytest

from qebench.utils.dataset import _extract_glossary_terms, load_glossary


class TestExtractGlossaryTerms:
    def test_action_translation_format(self) -> None:
        data = {
            "version": "1.0",
            "description": "Test glossary",
            "terms": [
                {"en": "Bellman equation", "zh-cn": "贝尔曼方程"},
                {"en": "Value function", "zh-cn": "价值函数"},
            ],
        }
        terms = _extract_glossary_terms(data)
        assert len(terms) == 2
        assert terms[0]["en"] == "Bellman equation"

    def test_bare_list_format(self) -> None:
        data = [
            {"en": "Bellman equation", "zh-cn": "贝尔曼方程"},
        ]
        terms = _extract_glossary_terms(data)
        assert len(terms) == 1

    def test_empty_dict(self) -> None:
        assert _extract_glossary_terms({}) == []

    def test_empty_list(self) -> None:
        assert _extract_glossary_terms([]) == []


class TestLoadGlossary:
    def test_null_glossary_path(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "qebench.utils.dataset.load_config",
            lambda: {"glossary_path": None},
        )
        assert load_glossary() == []

    def test_missing_glossary_path(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "qebench.utils.dataset.load_config",
            lambda: {},
        )
        assert load_glossary() == []

    def test_local_file(self, tmp_path, monkeypatch) -> None:
        glossary_file = tmp_path / "glossary.json"
        glossary_file.write_text(
            json.dumps({
                "version": "1.0",
                "terms": [{"en": "GDP", "zh-cn": "国内生产总值"}],
            }),
            encoding="utf-8",
        )
        monkeypatch.setattr(
            "qebench.utils.dataset.load_config",
            lambda: {"glossary_path": str(glossary_file)},
        )
        terms = load_glossary()
        assert len(terms) == 1
        assert terms[0]["en"] == "GDP"

    def test_local_file_not_found(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(
            "qebench.utils.dataset.load_config",
            lambda: {"glossary_path": str(tmp_path / "missing.json")},
        )
        assert load_glossary() == []

    def test_url_with_cache(self, tmp_path, monkeypatch) -> None:
        """When cache exists, URL is not fetched."""
        cache_dir = tmp_path / ".cache"
        cache_dir.mkdir()
        cache_file = cache_dir / "glossary.json"
        cache_file.write_text(
            json.dumps({"terms": [{"en": "inflation", "zh-cn": "通货膨胀"}]}),
            encoding="utf-8",
        )
        monkeypatch.setattr("qebench.utils.dataset.CACHE_DIR", cache_dir)
        monkeypatch.setattr(
            "qebench.utils.dataset.load_config",
            lambda: {"glossary_path": "https://example.com/glossary.json"},
        )
        terms = load_glossary()
        assert len(terms) == 1
        assert terms[0]["en"] == "inflation"

    def test_url_force_refresh_skips_cache(self, tmp_path, monkeypatch) -> None:
        """force_refresh=True should attempt a fetch even when cache exists."""
        cache_dir = tmp_path / ".cache"
        cache_dir.mkdir()
        cache_file = cache_dir / "glossary.json"
        cache_file.write_text(
            json.dumps({"terms": [{"en": "old", "zh-cn": "旧"}]}),
            encoding="utf-8",
        )
        monkeypatch.setattr("qebench.utils.dataset.CACHE_DIR", cache_dir)
        monkeypatch.setattr(
            "qebench.utils.dataset.load_config",
            lambda: {"glossary_path": "https://example.com/glossary.json"},
        )

        # Mock urlopen to fail — should fall back to cache
        def _bad_urlopen(*args, **kwargs):
            raise ConnectionError("mock network failure")

        monkeypatch.setattr("urllib.request.urlopen", _bad_urlopen)
        terms = load_glossary(force_refresh=True)
        # Falls back to cache on network failure
        assert len(terms) == 1
        assert terms[0]["en"] == "old"
