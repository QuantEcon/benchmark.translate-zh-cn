"""validate command — Validate all dataset JSON files against Pydantic models.

Loads every JSON file in data/terms/, data/sentences/, data/paragraphs/
and validates each entry against the corresponding Pydantic model.
Reports all errors, then exits non-zero if any were found.
Suitable for CI usage.
"""

from __future__ import annotations

import json
import sys

from pydantic import ValidationError

from qebench.models import Paragraph, Sentence, Term
from qebench.scoring.alignment import check_pair
from qebench.utils.dataset import DATA_DIR
from qebench.utils.display import console

# Map subdirectory names to their Pydantic model
_MODELS = {
    "terms": Term,
    "sentences": Sentence,
    "paragraphs": Paragraph,
}

# Terms are a headword and its translation, with no markers or comparable
# length, so the alignment signals do not apply to them.
_ALIGNMENT_TYPES = ("sentences", "paragraphs")


def _alignment_warnings(items: list, rel: str) -> list[str]:
    """Flag entries whose zh reference may not be a translation of its en.

    Eight entries were seeded misaligned (#31) and nothing caught it until
    the references had already been judged against.  These are warnings, not
    errors: the check is a heuristic, and it flagged one correct entry out of
    17 before it was tuned, so it should prompt review rather than block a
    contributor.  Use ``--strict`` to fail on them.
    """
    warnings: list[str] = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        problems = check_pair(item.get("en", ""), item.get("zh", ""))
        if problems:
            warnings.append(f"  {rel}[{i}] ({item.get('id', '?')}): {'; '.join(problems)}")
    return warnings


def validate(strict: bool = False) -> None:
    """Validate all dataset files against Pydantic schemas.

    The CLI wrapper lives in :mod:`qebench.cli`; a plain default is used here
    so the function stays directly callable, since a ``typer.Option`` default
    would arrive as a truthy ``OptionInfo`` sentinel.
    """
    errors: list[str] = []
    warnings: list[str] = []
    total_files = 0
    total_entries = 0

    for subdir, model_class in _MODELS.items():
        directory = DATA_DIR / subdir
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.json")):
            total_files += 1
            rel = path.relative_to(DATA_DIR.parent)
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
            except json.JSONDecodeError as exc:
                errors.append(f"  {rel}: invalid JSON — {exc}")
                continue

            if isinstance(data, list):
                items = data
            elif isinstance(data, dict):
                items = data.get("entries", [])
            else:
                errors.append(
                    f"  {rel}: invalid top-level JSON type "
                    f"{type(data).__name__} — expected list or object"
                )
                continue

            for i, item in enumerate(items):
                total_entries += 1
                if not isinstance(item, dict):
                    errors.append(
                        f"  {rel}[{i}] (?): invalid entry type "
                        f"{type(item).__name__}, expected object"
                    )
                    continue
                try:
                    model_class.model_validate(item)
                except ValidationError as exc:
                    for err in exc.errors():
                        loc = " → ".join(str(part) for part in err["loc"])
                        errors.append(
                            f"  {rel}[{i}] ({item.get('id', '?')}): "
                            f"{loc} — {err['msg']}"
                        )

            if subdir in _ALIGNMENT_TYPES:
                warnings.extend(_alignment_warnings(items, str(rel)))

    if warnings:
        label = "error" if strict else "warning"
        colour = "red" if strict else "yellow"
        console.print(
            f"\n[{colour} bold]en/zh alignment — {len(warnings)} {label}(s):[/{colour} bold]\n"
        )
        for warning in warnings:
            console.print(f"[{colour}]{warning}[/{colour}]")
        console.print(
            "\n[dim]Review with: uv run python scripts/audit_alignment.py --show-text[/dim]"
        )
        if strict:
            errors.extend(warnings)

    if errors:
        console.print(f"\n[red bold]Validation failed — {len(errors)} error(s):[/red bold]\n")
        for err in errors:
            console.print(f"[red]{err}[/red]")
        console.print()
        sys.exit(1)
    else:
        console.print(
            f"\n[green]✓ All valid — {total_entries} entries in {total_files} files[/green]\n"
        )
