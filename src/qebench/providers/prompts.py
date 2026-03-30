"""Prompt template loading and validation."""

from __future__ import annotations

from pathlib import Path

_PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "prompts"

_REQUIRED_PLACEHOLDERS = {"{text}", "{source_lang}", "{target_lang}", "{domain}"}


def list_templates() -> list[str]:
    """Return names of available prompt templates (without .txt extension)."""
    if not _PROMPTS_DIR.exists():
        return []
    return sorted(p.stem for p in _PROMPTS_DIR.glob("*.txt") if p.stem != ".gitkeep")


def load_template(name: str = "default") -> str:
    """Load a prompt template by name.

    Args:
        name: Template name (without .txt extension).

    Returns:
        The template string with {text}, {source_lang}, {target_lang}, {domain} placeholders.

    Raises:
        FileNotFoundError: If the template doesn't exist.
        ValueError: If required placeholders are missing.
    """
    path = _PROMPTS_DIR / f"{name}.txt"
    if not path.exists():
        available = list_templates()
        raise FileNotFoundError(
            f"Prompt template '{name}' not found. "
            f"Available: {', '.join(available) or '(none)'}"
        )

    template = path.read_text(encoding="utf-8")

    missing = _REQUIRED_PLACEHOLDERS - {p for p in _REQUIRED_PLACEHOLDERS if p in template}
    if missing:
        raise ValueError(
            f"Template '{name}' is missing required placeholders: {', '.join(sorted(missing))}"
        )

    return template
