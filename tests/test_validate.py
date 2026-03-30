"""Tests for the validate command."""

from __future__ import annotations

import json

import pytest

from qebench.commands.validate import validate


class TestValidate:
    def test_valid_dataset_passes(self, tmp_path, monkeypatch):
        """Valid entries should pass without error."""
        monkeypatch.setattr("qebench.commands.validate.DATA_DIR", tmp_path)
        terms_dir = tmp_path / "terms"
        terms_dir.mkdir()
        entries = [
            {"id": "term-001", "en": "inflation", "zh": "通货膨胀", "domain": "economics", "difficulty": "basic"},
            {"id": "term-002", "en": "GDP", "zh": "国内生产总值", "domain": "economics", "difficulty": "basic"},
        ]
        (terms_dir / "test.json").write_text(json.dumps(entries), encoding="utf-8")
        validate()  # Should not raise

    def test_invalid_entry_exits(self, tmp_path, monkeypatch):
        """An entry with invalid ID pattern should cause exit(1)."""
        monkeypatch.setattr("qebench.commands.validate.DATA_DIR", tmp_path)
        terms_dir = tmp_path / "terms"
        terms_dir.mkdir()
        entries = [
            {"id": "bad-id", "en": "x", "zh": "y", "domain": "d", "difficulty": "basic"},
        ]
        (terms_dir / "test.json").write_text(json.dumps(entries), encoding="utf-8")
        with pytest.raises(SystemExit):
            validate()

    def test_missing_field_exits(self, tmp_path, monkeypatch):
        """An entry missing required fields should cause exit(1)."""
        monkeypatch.setattr("qebench.commands.validate.DATA_DIR", tmp_path)
        terms_dir = tmp_path / "terms"
        terms_dir.mkdir()
        entries = [{"id": "term-001"}]  # missing en, zh, domain, difficulty
        (terms_dir / "test.json").write_text(json.dumps(entries), encoding="utf-8")
        with pytest.raises(SystemExit):
            validate()

    def test_invalid_json_exits(self, tmp_path, monkeypatch):
        """A file with invalid JSON should cause exit(1)."""
        monkeypatch.setattr("qebench.commands.validate.DATA_DIR", tmp_path)
        terms_dir = tmp_path / "terms"
        terms_dir.mkdir()
        (terms_dir / "test.json").write_text("{bad json", encoding="utf-8")
        with pytest.raises(SystemExit):
            validate()

    def test_empty_dataset_passes(self, tmp_path, monkeypatch):
        """No files at all should pass (nothing to validate)."""
        monkeypatch.setattr("qebench.commands.validate.DATA_DIR", tmp_path)
        validate()  # Should not raise

    def test_validates_sentences(self, tmp_path, monkeypatch):
        """Sentence entries should validate against Sentence model."""
        monkeypatch.setattr("qebench.commands.validate.DATA_DIR", tmp_path)
        sent_dir = tmp_path / "sentences"
        sent_dir.mkdir()
        entries = [
            {"id": "sent-001", "en": "Hello world.", "zh": "你好世界。", "domain": "general", "difficulty": "basic"},
        ]
        (sent_dir / "test.json").write_text(json.dumps(entries), encoding="utf-8")
        validate()  # Should not raise

    def test_validates_paragraphs(self, tmp_path, monkeypatch):
        """Paragraph entries should validate against Paragraph model."""
        monkeypatch.setattr("qebench.commands.validate.DATA_DIR", tmp_path)
        para_dir = tmp_path / "paragraphs"
        para_dir.mkdir()
        entries = [
            {"id": "para-001", "en": "A paragraph.", "zh": "一段话。", "domain": "general", "difficulty": "basic"},
        ]
        (para_dir / "test.json").write_text(json.dumps(entries), encoding="utf-8")
        validate()  # Should not raise
