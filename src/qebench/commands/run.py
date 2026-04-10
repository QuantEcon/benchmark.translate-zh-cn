"""run command — Batch translate dataset entries via LLM providers.

Loads entries from the dataset, translates them using the specified provider
and prompt template, then saves results to results/model-outputs/.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import typer
from rich.panel import Panel
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeRemainingColumn
from rich.table import Table

from qebench.providers.base import TranslationResult
from qebench.providers.prompts import load_template
from qebench.utils.dataset import DATA_DIR, RESULTS_DIR, load_all
from qebench.utils.display import console

MODEL_OUTPUTS_DIR = RESULTS_DIR / "model-outputs"

# Provider registry — maps name to (module_path, class_name)
_PROVIDERS: dict[str, tuple[str, str]] = {
    "claude": ("qebench.providers.claude", "ClaudeProvider"),
    "openai": ("qebench.providers.openai", "OpenAIProvider"),
}


def _get_provider(name: str, *, model: str | None = None):
    """Lazily import and instantiate a provider by name."""
    if name not in _PROVIDERS:
        available = ", ".join(sorted(_PROVIDERS))
        raise typer.BadParameter(f"Unknown provider '{name}'. Available: {available}")

    module_path, class_name = _PROVIDERS[name]
    import importlib

    mod = importlib.import_module(module_path)
    cls = getattr(mod, class_name)
    return cls(model=model)


def _save_results(results: list[TranslationResult], run_id: str, *, prompt_name: str) -> Path:
    """Save translation results to a JSONL file."""
    MODEL_OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    path = MODEL_OUTPUTS_DIR / f"{run_id}.jsonl"
    with open(path, "a", encoding="utf-8") as f:
        for r in results:
            record = {
                "entry_id": r.entry_id,
                "source_text": r.source_text,
                "translated_text": r.translated_text,
                "model": r.model,
                "provider": r.provider,
                "prompt_template": prompt_name,
                "input_tokens": r.input_tokens,
                "output_tokens": r.output_tokens,
                "cost_usd": round(r.cost_usd, 6),
                "latency_ms": round(r.latency_ms, 1),
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path


def run(
    provider: str = typer.Option("claude", "--provider", "-p", help="LLM provider: claude, openai."),
    model: str | None = typer.Option(None, "--model", "-m", help="Override the default model."),
    prompt: str = typer.Option("default", "--prompt", help="Prompt template name from prompts/."),
    count: int = typer.Option(0, "--count", "-n", help="Max entries to translate (0 = all)."),
    domain: str | None = typer.Option(None, "--domain", "-d", help="Filter by domain."),
    entry_type: str = typer.Option("terms", "--type", "-t", help="Entry type: terms, sentences, paragraphs."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview entries without calling the API."),
) -> None:
    """Batch translate dataset entries via an LLM provider."""
    # Load config for language pair
    from qebench.utils.dataset import load_config

    config = load_config()
    source_lang = config["language_pair"]["source"]
    target_lang = config["language_pair"]["target"]

    # Load prompt template
    template = load_template(prompt)

    # If template uses {glossary}, load and inject glossary terms
    if "{glossary}" in template:
        from qebench.utils.dataset import load_glossary

        glossary_terms = load_glossary()
        if glossary_terms:
            glossary_text = "\n".join(
                f"  {en} → {zh}" for en, zh in sorted(glossary_terms.items())
            )
        else:
            glossary_text = "(no glossary loaded)"
        template = template.replace("{glossary}", glossary_text)

    # Load entries
    terms, sentences, paragraphs = load_all()
    type_map = {"terms": terms, "sentences": sentences, "paragraphs": paragraphs}
    if entry_type not in type_map:
        raise typer.BadParameter(f"Unknown type '{entry_type}'. Use: terms, sentences, paragraphs.")
    entries = type_map[entry_type]

    if domain:
        entries = [e for e in entries if e.domain == domain]

    if not entries:
        console.print("[yellow]No entries found matching filters.[/yellow]")
        raise typer.Exit()

    if count > 0:
        entries = entries[:count]

    # Prepare text dicts for the provider
    texts = [{"id": e.id, "text": e.en, "domain": e.domain} for e in entries]

    console.print()
    console.print(
        Panel(
            f"[bold]Provider:[/bold] {provider}\n"
            f"[bold]Model:[/bold] {model or '(default)'}\n"
            f"[bold]Prompt:[/bold] {prompt}\n"
            f"[bold]Entries:[/bold] {len(texts)} {entry_type}"
            + (f" ({domain})" if domain else ""),
            title="qebench run",
            border_style="blue",
        )
    )

    if dry_run:
        console.print("\n[dim]Dry run — no API calls will be made.[/dim]")
        for t in texts[:5]:
            console.print(f"  {t['id']}: {t['text'][:60]}...")
        if len(texts) > 5:
            console.print(f"  ... and {len(texts) - 5} more")
        return

    # Instantiate provider
    llm = _get_provider(provider, model=model)

    # Run translations via batch API
    run_id = f"{provider}-{llm.model}-{prompt}-{int(time.time())}"

    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(f"Translating {len(texts)} entries", total=len(texts))

        def _on_complete(_result):
            progress.advance(task)

        results = llm.translate_batch(
            texts,
            source_lang=source_lang,
            target_lang=target_lang,
            prompt_template=template,
            on_complete=_on_complete,
        )

    # Save results
    output_path = _save_results(results, run_id, prompt_name=prompt)

    # Summary
    total_cost = sum(r.cost_usd for r in results)
    total_tokens = sum(r.input_tokens + r.output_tokens for r in results)
    avg_latency = sum(r.latency_ms for r in results) / len(results) if results else 0

    summary = Table(title="Run Summary", border_style="green")
    summary.add_column("Metric", style="bold")
    summary.add_column("Value", justify="right")
    summary.add_row("Entries translated", str(len(results)))
    summary.add_row("Total tokens", f"{total_tokens:,}")
    summary.add_row("Total cost", f"${total_cost:.4f}")
    summary.add_row("Avg latency", f"{avg_latency:.0f}ms")
    summary.add_row("Output file", str(output_path.relative_to(DATA_DIR.parent)))

    console.print()
    console.print(summary)
