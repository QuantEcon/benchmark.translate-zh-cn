"""Dataset loading and saving utilities."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from qebench.models import Paragraph, Sentence, Term

T = TypeVar("T", Term, Sentence, Paragraph)

# Resolve data/ directory relative to repo root
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR = _REPO_ROOT / "data"
RESULTS_DIR = _REPO_ROOT / "results"
CONFIG_PATH = _REPO_ROOT / "config.yaml"


def _load_entries(directory: Path, model_class: type[T]) -> list[T]:
    """Load all entries of a given type from JSON files in a directory."""
    entries: list[T] = []
    if not directory.exists():
        return entries
    for path in sorted(directory.glob("*.json")):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        # Support both bare list and {version, entries} wrapper
        items = data if isinstance(data, list) else data.get("entries", [])
        for item in items:
            entries.append(model_class.model_validate(item))
    return entries


def load_terms() -> list[Term]:
    return _load_entries(DATA_DIR / "terms", Term)


def load_sentences() -> list[Sentence]:
    return _load_entries(DATA_DIR / "sentences", Sentence)


def load_paragraphs() -> list[Paragraph]:
    return _load_entries(DATA_DIR / "paragraphs", Paragraph)


def load_all() -> tuple[list[Term], list[Sentence], list[Paragraph]]:
    return load_terms(), load_sentences(), load_paragraphs()


def save_entries(entries: list[BaseModel], path: Path) -> None:
    """Save a list of Pydantic model entries to a JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = [entry.model_dump(exclude_none=True) for entry in entries]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def load_config() -> dict:
    """Load config.yaml from repo root."""
    import yaml

    if not CONFIG_PATH.exists():
        return {}
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def get_domains() -> list[str]:
    """Get the list of valid domains from config."""
    config = load_config()
    return config.get("domains", [])


def get_targets() -> dict[str, int]:
    """Get dataset size targets from config."""
    config = load_config()
    return config.get("targets", {"terms": 500, "sentences": 100, "paragraphs": 30})
