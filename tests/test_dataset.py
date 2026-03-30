"""Tests for dataset loading/saving utilities."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from qebench.models import Term
from qebench.utils.dataset import _load_entries, save_entries


class TestLoadEntries:
    def test_load_bare_list(self, sample_terms_file: Path) -> None:
        terms = _load_entries(sample_terms_file / "terms", Term)
        assert len(terms) == 2
        assert terms[0].en == "Bellman equation"
        assert terms[1].en == "Markov chain"

    def test_load_wrapped_format(self, tmp_data_dir: Path) -> None:
        data = {
            "version": "1.0",
            "entries": [
                {
                    "id": "term-001",
                    "en": "GDP",
                    "zh": "国内生产总值",
                    "domain": "macroeconomics",
                    "difficulty": "basic",
                }
            ],
        }
        path = tmp_data_dir / "terms" / "macro.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)

        terms = _load_entries(tmp_data_dir / "terms", Term)
        assert len(terms) == 1
        assert terms[0].zh == "国内生产总值"

    def test_load_empty_directory(self, tmp_data_dir: Path) -> None:
        terms = _load_entries(tmp_data_dir / "terms", Term)
        assert terms == []

    def test_load_nonexistent_directory(self, tmp_path: Path) -> None:
        terms = _load_entries(tmp_path / "nonexistent", Term)
        assert terms == []

    def test_load_multiple_files(self, tmp_data_dir: Path) -> None:
        for name, entry in [
            ("a.json", {"id": "term-001", "en": "A", "zh": "甲", "domain": "economics", "difficulty": "basic"}),
            ("b.json", {"id": "term-002", "en": "B", "zh": "乙", "domain": "economics", "difficulty": "basic"}),
        ]:
            with open(tmp_data_dir / "terms" / name, "w") as f:
                json.dump([entry], f)

        terms = _load_entries(tmp_data_dir / "terms", Term)
        assert len(terms) == 2
        # Files loaded in sorted order
        assert terms[0].en == "A"
        assert terms[1].en == "B"


class TestSaveEntries:
    def test_save_and_reload(self, tmp_path: Path) -> None:
        terms = [
            Term(
                id="term-001",
                en="test",
                zh="测试",
                domain="economics",
                difficulty="basic",
            )
        ]
        path = tmp_path / "output" / "test.json"
        save_entries(terms, path)

        assert path.exists()
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        assert len(data) == 1
        assert data[0]["en"] == "test"

    def test_save_chinese_characters_not_escaped(self, tmp_path: Path) -> None:
        terms = [
            Term(
                id="term-001",
                en="test",
                zh="贝尔曼方程",
                domain="economics",
                difficulty="basic",
            )
        ]
        path = tmp_path / "test.json"
        save_entries(terms, path)

        raw = path.read_text(encoding="utf-8")
        assert "贝尔曼方程" in raw
        assert "\\u" not in raw
