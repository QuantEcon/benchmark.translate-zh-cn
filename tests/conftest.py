"""Shared pytest fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture()
def tmp_data_dir(tmp_path: Path) -> Path:
    """Create a temporary data directory with subdirectories."""
    for subdir in ("terms", "sentences", "paragraphs"):
        (tmp_path / subdir).mkdir()
    return tmp_path


@pytest.fixture()
def sample_terms() -> list[dict]:
    return [
        {
            "id": "term-001",
            "en": "Bellman equation",
            "zh": "贝尔曼方程",
            "domain": "dynamic-programming",
            "difficulty": "intermediate",
            "alternatives": ["贝尔曼等式"],
            "source": "quantecon/dp-intro",
        },
        {
            "id": "term-002",
            "en": "Markov chain",
            "zh": "马尔可夫链",
            "domain": "stochastic-processes",
            "difficulty": "basic",
            "alternatives": [],
            "source": "",
        },
    ]


@pytest.fixture()
def sample_terms_file(tmp_data_dir: Path, sample_terms: list[dict]) -> Path:
    """Write sample terms to a JSON file and return the terms dir."""
    path = tmp_data_dir / "terms" / "test.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sample_terms, f, ensure_ascii=False, indent=2)
    return tmp_data_dir
