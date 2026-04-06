"""add command — Contribute new entries to the dataset interactively."""

from __future__ import annotations

import json
from pathlib import Path

import questionary
from rich.panel import Panel
from rich.text import Text

from qebench import __version__
from qebench.models import Difficulty, Paragraph, Sentence, Term
from qebench.utils.dataset import DATA_DIR, get_domains, load_all
from qebench.utils.display import console
from qebench.utils.github import get_github_username


def _next_id(prefix: str, existing: list) -> str:
    """Generate the next sequential ID for a given prefix."""
    max_num = 0
    for entry in existing:
        try:
            num = int(entry.id.split("-")[1])
            max_num = max(max_num, num)
        except (IndexError, ValueError):
            continue
    return f"{prefix}-{max_num + 1:03d}"


def _find_duplicates(en: str, existing: list[Term | Sentence | Paragraph]) -> list[Term | Sentence | Paragraph]:
    """Return existing entries whose English text matches *en* (case-insensitive)."""
    normalised = en.strip().lower()
    return [e for e in existing if e.en.strip().lower() == normalised]


def _warn_duplicates(duplicates: list[Term | Sentence | Paragraph]) -> bool:
    """Show duplicate entries and ask whether to continue. Returns True to proceed."""
    console.print(f"\n[yellow]⚠ Found {len(duplicates)} existing entry with the same English text:[/yellow]")
    for dup in duplicates:
        zh = getattr(dup, "zh", None) or ""
        console.print(f"  [dim]{dup.id}[/dim]  {dup.en}  →  {zh}  [dim]({dup.domain})[/dim]")
    return questionary.confirm("Add anyway?", default=False).ask() or False


def _save_to_user_file(entry: Term | Sentence | Paragraph, entry_type: str, username: str) -> Path:
    """Append an entry to the user's data file."""
    type_dir = DATA_DIR / entry_type
    type_dir.mkdir(parents=True, exist_ok=True)
    filepath = type_dir / f"{username}.json"

    entries: list[dict] = []
    if filepath.exists():
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)
        entries = data if isinstance(data, list) else data.get("entries", [])

    entry_dict = entry.model_dump(exclude_none=True)
    entry_dict["cli_version"] = __version__
    entries.append(entry_dict)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)
        f.write("\n")

    return filepath


def _add_term(domains: list[str], existing_terms: list[Term]) -> Term | None:
    """Interactively collect a new term entry."""
    console.print("\n[bold cyan]Add a new term[/bold cyan]\n")

    en = questionary.text("English term:").ask()
    if not en:
        return None

    duplicates = _find_duplicates(en, existing_terms)
    if duplicates and not _warn_duplicates(duplicates):
        return None

    zh = questionary.text("Chinese translation (中文):").ask()
    if not zh:
        return None

    domain = questionary.select("Domain:", choices=domains).ask()
    if not domain:
        return None

    difficulty = questionary.select(
        "Difficulty:", choices=["basic", "intermediate", "advanced"]
    ).ask()
    if not difficulty:
        return None

    alt_text = questionary.text(
        "Alternative translations (comma-separated, or empty):"
    ).ask()
    alternatives = [a.strip() for a in alt_text.split(",") if a.strip()] if alt_text else []

    source = questionary.text("Source reference (optional):").ask() or ""

    term_id = _next_id("term", existing_terms)
    return Term(
        id=term_id,
        en=en,
        zh=zh,
        domain=domain,
        difficulty=Difficulty(difficulty),
        alternatives=alternatives,
        source=source,
    )


def _add_sentence(domains: list[str], existing_sentences: list[Sentence]) -> Sentence | None:
    """Interactively collect a new sentence entry."""
    console.print("\n[bold cyan]Add a new sentence[/bold cyan]\n")

    en = questionary.text("English sentence:").ask()
    if not en:
        return None

    duplicates = _find_duplicates(en, existing_sentences)
    if duplicates and not _warn_duplicates(duplicates):
        return None

    zh = questionary.text("Chinese translation (中文):").ask()
    if not zh:
        return None

    domain = questionary.select("Domain:", choices=domains).ask()
    if not domain:
        return None

    difficulty = questionary.select(
        "Difficulty:", choices=["basic", "intermediate", "advanced"]
    ).ask()
    if not difficulty:
        return None

    source = questionary.text("Source reference (optional):").ask() or ""

    sent_id = _next_id("sent", existing_sentences)
    return Sentence(
        id=sent_id,
        en=en,
        zh=zh,
        domain=domain,
        difficulty=Difficulty(difficulty),
        source=source,
    )


def _add_paragraph(domains: list[str], existing_paragraphs: list[Paragraph]) -> Paragraph | None:
    """Interactively collect a new paragraph entry."""
    console.print("\n[bold cyan]Add a new paragraph[/bold cyan]\n")

    en = questionary.text("English paragraph:").ask()
    if not en:
        return None

    duplicates = _find_duplicates(en, existing_paragraphs)
    if duplicates and not _warn_duplicates(duplicates):
        return None

    zh = questionary.text("Chinese translation (中文):").ask()
    if not zh:
        return None

    domain = questionary.select("Domain:", choices=domains).ask()
    if not domain:
        return None

    difficulty = questionary.select(
        "Difficulty:", choices=["basic", "intermediate", "advanced"]
    ).ask()
    if not difficulty:
        return None

    contains_math = questionary.confirm("Contains math?", default=False).ask()
    contains_code = questionary.confirm("Contains code?", default=False).ask()
    source = questionary.text("Source reference (optional):").ask() or ""

    para_id = _next_id("para", existing_paragraphs)
    return Paragraph(
        id=para_id,
        en=en,
        zh=zh,
        domain=domain,
        difficulty=Difficulty(difficulty),
        contains_math=contains_math or False,
        contains_code=contains_code or False,
        source=source,
    )


def add() -> None:
    """Contribute new terms, sentences, or paragraphs to the dataset."""
    username = get_github_username()
    domains = get_domains()
    if not domains:
        console.print("[red]No domains found in config.yaml[/red]")
        raise SystemExit(1)

    terms, sentences, paragraphs = load_all()

    entry_type = questionary.select(
        "What would you like to add?",
        choices=["term", "sentence", "paragraph"],
    ).ask()

    if not entry_type:
        return

    builders = {
        "term": lambda: _add_term(domains, terms),
        "sentence": lambda: _add_sentence(domains, sentences),
        "paragraph": lambda: _add_paragraph(domains, paragraphs),
    }

    entry = builders[entry_type]()
    if entry is None:
        console.print("[yellow]Cancelled.[/yellow]")
        return

    # Show preview
    preview = Text()
    preview.append(f"  ID:         {entry.id}\n", style="dim")
    preview.append(f"  English:    {entry.en}\n")
    preview.append(f"  Chinese:    {entry.zh}\n")  # type: ignore[union-attr]
    preview.append(f"  Domain:     {entry.domain}\n", style="cyan")
    preview.append(f"  Difficulty: {entry.difficulty.value}\n", style="yellow")
    console.print()
    console.print(Panel(preview, title="[bold]Preview[/bold]", border_style="green"))

    confirm = questionary.confirm("Save this entry?", default=True).ask()
    if not confirm:
        console.print("[yellow]Discarded.[/yellow]")
        return

    type_plural = {"term": "terms", "sentence": "sentences", "paragraph": "paragraphs"}
    filepath = _save_to_user_file(entry, type_plural[entry_type], username)
    console.print(f"\n[green]✓ Saved {entry.id} to {filepath.name}[/green]")

    # Ask to continue
    again = questionary.confirm("Add another?", default=True).ask()
    if again:
        add()
