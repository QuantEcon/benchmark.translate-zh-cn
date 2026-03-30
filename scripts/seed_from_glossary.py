#!/usr/bin/env python3
"""Seed the benchmark dataset from action-translation's glossary/zh-cn.json.

Usage:
    python scripts/seed_from_glossary.py /path/to/glossary/zh-cn.json

Converts glossary terms into benchmark Term format and writes them to
data/terms/ JSON files grouped by domain.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

# Map glossary "context" values to benchmark domain slugs.
# Unmapped contexts go to a fallback based on simple rules.
CONTEXT_TO_DOMAIN: dict[str, str] = {
    "economics": "economics",
    "macroeconomics": "macroeconomics",
    "macroeconomics abbreviation": "macroeconomics",
    "microeconomics": "microeconomics",
    "finance": "finance",
    "monetary economics": "finance",
    "monetary policy": "finance",
    "banking": "finance",
    "options": "finance",
    "derivatives": "finance",
    "public finance": "economics",
    "welfare economics": "economics",
    "labor economics": "economics",
    "economic policy": "economics",
    "economic history": "economics",
    "economic history abbreviation": "economics",
    "income distribution": "economics",
    "production economics": "economics",
    "international economics": "economics",
    "international comparison": "economics",
    "business cycles": "macroeconomics",
    "growth theory": "macroeconomics",
    "input-output economics": "economics",
    "dynamic programming": "dynamic-programming",
    "optimization": "optimization",
    "dynamic systems": "dynamic-programming",
    "dynamical systems": "dynamic-programming",
    "game theory": "game-theory",
    "mathematics": "mathematics",
    "calculus": "calculus",
    "trigonometry": "calculus",
    "linear algebra": "linear-algebra",
    "functional analysis": "mathematics",
    "complex analysis": "mathematics",
    "difference equations": "mathematics",
    "differential equations": "mathematics",
    "statistics": "statistics",
    "probability": "probability",
    "probability abbreviation": "probability",
    "stochastic processes": "stochastic-processes",
    "Markov chains": "stochastic-processes",
    "time series": "statistics",
    "econometrics": "statistics",
    "econometrics abbreviation": "statistics",
    "kernel density estimation": "statistics",
    "kernel methods": "statistics",
    "numerical computation": "numerical-methods",
    "numerical methods": "numerical-methods",
    "simulation": "numerical-methods",
    "simulation methods": "numerical-methods",
    "graph theory": "mathematics",
    "network science": "mathematics",
    "data visualization": "other",
    "data source": "other",
    "educational content": "other",
    "institution": "other",
}

# Skip name entries (people, not terms)
SKIP_CONTEXTS = {
    "economist name",
    "economic historian name",
    "mathematician name",
    "historian name",
    "researcher name",
    "economics abbreviation",
}


def map_domain(context: str) -> str | None:
    """Map a glossary context to a benchmark domain. Returns None to skip."""
    if context in SKIP_CONTEXTS:
        return None
    return CONTEXT_TO_DOMAIN.get(context, "other")


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/seed_from_glossary.py <glossary-path>")
        sys.exit(1)

    glossary_path = Path(sys.argv[1])
    if not glossary_path.exists():
        print(f"Error: {glossary_path} not found")
        sys.exit(1)

    with open(glossary_path, encoding="utf-8") as f:
        glossary = json.load(f)

    terms = glossary.get("terms", [])
    print(f"Loading {len(terms)} glossary terms...")

    # Group by domain
    by_domain: dict[str, list[dict]] = defaultdict(list)
    skipped = 0

    for i, term in enumerate(terms):
        context = term.get("context", "")
        domain = map_domain(context)
        if domain is None:
            skipped += 1
            continue

        term_id = f"term-{len(by_domain[domain]) + 1:03d}"
        # Check for duplicate — recompute after grouping
        entry = {
            "id": term_id,
            "en": term["en"],
            "zh": term.get("zh-cn", term.get("zh", "")),
            "domain": domain,
            "difficulty": "intermediate",  # Default; can be refined later
            "alternatives": [],
            "source": f"glossary/zh-cn ({context})",
        }
        by_domain[domain].append(entry)

    # Reassign IDs sequentially across all domains for global uniqueness
    global_idx = 1
    for domain in sorted(by_domain.keys()):
        for entry in by_domain[domain]:
            entry["id"] = f"term-{global_idx:03d}"
            global_idx += 1

    # Write output files
    output_dir = Path(__file__).resolve().parent.parent / "data" / "terms"
    output_dir.mkdir(parents=True, exist_ok=True)

    total = 0
    for domain, entries in sorted(by_domain.items()):
        filename = domain.replace("-", "_") + ".json"
        out_path = output_dir / filename
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)
            f.write("\n")
        total += len(entries)
        print(f"  {domain}: {len(entries)} terms → {out_path.name}")

    print(f"\nDone: {total} terms written, {skipped} skipped (names/abbreviations)")


if __name__ == "__main__":
    main()
