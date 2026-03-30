"""Tests for prompt template loading."""

from __future__ import annotations

import pytest

from qebench.providers.prompts import list_templates, load_template


class TestListTemplates:
    def test_returns_list(self) -> None:
        templates = list_templates()
        assert isinstance(templates, list)

    def test_includes_default(self) -> None:
        templates = list_templates()
        assert "default" in templates

    def test_includes_academic(self) -> None:
        templates = list_templates()
        assert "academic" in templates

    def test_empty_when_dir_missing(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr("qebench.providers.prompts._PROMPTS_DIR", tmp_path / "nonexistent")
        assert list_templates() == []


class TestLoadTemplate:
    def test_loads_default(self) -> None:
        template = load_template("default")
        assert "{text}" in template
        assert "{source_lang}" in template
        assert "{target_lang}" in template
        assert "{domain}" in template

    def test_loads_academic(self) -> None:
        template = load_template("academic")
        assert "{text}" in template
        assert "academic" in template.lower()

    def test_missing_template_raises(self) -> None:
        with pytest.raises(FileNotFoundError, match="not found"):
            load_template("nonexistent-template-xyz")

    def test_missing_placeholders_raises(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr("qebench.providers.prompts._PROMPTS_DIR", tmp_path)
        (tmp_path / "bad.txt").write_text("Just translate this.", encoding="utf-8")
        with pytest.raises(ValueError, match="missing required placeholders"):
            load_template("bad")
