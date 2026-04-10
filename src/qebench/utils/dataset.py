"""Dataset loading and saving utilities."""

from __future__ import annotations

import json
import logging
import urllib.request
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
CACHE_DIR = _REPO_ROOT / ".cache"

_logger = logging.getLogger(__name__)


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


def load_glossary(*, force_refresh: bool = False) -> list[dict]:
    """Load the translation glossary from config.yaml ``glossary_path``.

    Supports both local file paths and HTTPS URLs.  When fetching from a
    URL the result is cached to ``.cache/glossary.json`` so that offline
    use and CI still work.  Pass *force_refresh=True* (or delete the
    cache file) to re-fetch.

    Returns a list of term dicts, each with at least ``en`` and a
    target-language key (e.g. ``zh-cn``).  Returns an empty list when
    ``glossary_path`` is ``None`` or not set.
    """
    config = load_config()
    glossary_path: str | None = config.get("glossary_path")
    if not glossary_path:
        return []

    cache_file = CACHE_DIR / "glossary.json"

    # URL path — fetch (with cache)
    if glossary_path.startswith(("https://", "http://")):
        if not force_refresh and cache_file.exists():
            with open(cache_file, encoding="utf-8") as f:
                data = json.load(f)
            return _extract_glossary_terms(data)

        try:
            req = urllib.request.Request(glossary_path)
            with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310
                raw = resp.read().decode("utf-8")
            data = json.loads(raw)
            # Cache for offline use
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(cache_file, "w", encoding="utf-8") as f:
                f.write(raw)
            return _extract_glossary_terms(data)
        except Exception:
            _logger.warning("Failed to fetch glossary from %s", glossary_path)
            # Fall back to cache if available
            if cache_file.exists():
                _logger.info("Using cached glossary from %s", cache_file)
                with open(cache_file, encoding="utf-8") as f:
                    data = json.load(f)
                return _extract_glossary_terms(data)
            return []

    # Local file path
    local = Path(glossary_path)
    if not local.is_absolute():
        local = _REPO_ROOT / local
    if not local.exists():
        _logger.warning("Glossary file not found: %s", local)
        return []

    with open(local, encoding="utf-8") as f:
        data = json.load(f)
    return _extract_glossary_terms(data)


def _extract_glossary_terms(data: dict | list) -> list[dict]:
    """Extract term entries from glossary JSON.

    Supports the action-translation format ``{version, description, terms: [...]}``
    and bare lists.
    """
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "terms" in data:
        return data["terms"]
    return []
