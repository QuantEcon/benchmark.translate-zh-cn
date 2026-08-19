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


class TestAlignmentCheck:
    """`qebench validate` surfaces the misalignment that produced #31.

    Warnings by default, errors under --strict: the check is a heuristic and
    should prompt review rather than block a contributor mid-session.
    """

    def _write_paragraph(self, tmp_path, monkeypatch, en: str, zh: str) -> None:
        monkeypatch.setattr("qebench.commands.validate.DATA_DIR", tmp_path)
        paras = tmp_path / "paragraphs"
        paras.mkdir()
        entry = {
            "id": "para-001",
            "en": en,
            "zh": zh,
            "domain": "economics",
            "difficulty": "basic",
        }
        (paras / "seed.json").write_text(json.dumps([entry], ensure_ascii=False), encoding="utf-8")

    def test_misaligned_entry_warns_but_passes(self, tmp_path, monkeypatch, capsys):
        """The para-007 shape: four list items rendered as one."""
        self._write_paragraph(
            tmp_path,
            monkeypatch,
            "1. the determinant of $A$ equals the product 2. the trace of $A$ equals "
            "the sum 3. if $A$ is symmetric all eigenvalues are real 4. the "
            "eigenvalues of $A^{-1}$ are $1/\\lambda_1$",
            "1. $A$ 的行列式等于其特征值的乘积",
        )
        validate()  # warns, does not raise
        out = capsys.readouterr().out
        assert "alignment" in out
        assert "para-001" in out

    def test_misaligned_entry_fails_under_strict(self, tmp_path, monkeypatch):
        self._write_paragraph(
            tmp_path,
            monkeypatch,
            "1. the determinant of $A$ equals the product 2. the trace of $A$ equals "
            "the sum 3. if $A$ is symmetric all eigenvalues are real 4. the "
            "eigenvalues of $A^{-1}$ are $1/\\lambda_1$",
            "1. $A$ 的行列式等于其特征值的乘积",
        )
        with pytest.raises(SystemExit) as exc:
            validate(strict=True)
        assert exc.value.code == 1

    def test_aligned_entry_is_silent(self, tmp_path, monkeypatch, capsys):
        self._write_paragraph(
            tmp_path,
            monkeypatch,
            "Given the dynamics in {eq}`ar1_ma` and initial conditions $\\mu_0, v_0$, "
            "we obtain $\\mu_t, v_t$ and hence",
            "给定 {eq}`ar1_ma` 中的动态和初始条件 $\\mu_0, v_0$，我们得到 $\\mu_t, v_t$，因此",
        )
        validate()
        assert "alignment" not in capsys.readouterr().out

    def test_terms_are_not_alignment_checked(self, tmp_path, monkeypatch, capsys):
        """A headword and its translation have no markers and no comparable length."""
        monkeypatch.setattr("qebench.commands.validate.DATA_DIR", tmp_path)
        terms = tmp_path / "terms"
        terms.mkdir()
        entry = {
            "id": "term-001",
            "en": "Present discounted value",
            "zh": "现值",
            "domain": "finance",
            "difficulty": "basic",
        }
        (terms / "seed.json").write_text(json.dumps([entry], ensure_ascii=False), encoding="utf-8")
        validate()
        assert "alignment" not in capsys.readouterr().out
