"""Judgment results persistence — Elo ratings and judgment records.

Stores per-user judgment JSONL files and a shared elo.json.
"""

from __future__ import annotations

import json
from pathlib import Path

from qebench.scoring.elo import DEFAULT_RATING, update_elo

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
JUDGMENTS_DIR = _REPO_ROOT / "results" / "judgments"
ELO_PATH = _REPO_ROOT / "results" / "elo.json"


def load_elo_ratings() -> dict[str, float]:
    """Load model Elo ratings from elo.json.

    Returns:
        Dict mapping model name to Elo rating.
    """
    if not ELO_PATH.exists():
        return {}
    with open(ELO_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_elo_ratings(ratings: dict[str, float]) -> None:
    """Persist model Elo ratings to elo.json."""
    ELO_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(ELO_PATH, "w", encoding="utf-8") as f:
        json.dump(ratings, f, indent=2, ensure_ascii=False)
        f.write("\n")


def record_judgment(
    *,
    username: str,
    entry_id: str,
    model_a: str,
    model_b: str,
    winner: str,
    score_a_accuracy: int,
    score_a_fluency: int,
    score_b_accuracy: int,
    score_b_fluency: int,
    timestamp: str,
    cli_version: str,
) -> None:
    """Append a judgment record to the user's JSONL file."""
    JUDGMENTS_DIR.mkdir(parents=True, exist_ok=True)
    path = JUDGMENTS_DIR / f"{username}.jsonl"

    record = {
        "entry_id": entry_id,
        "model_a": model_a,
        "model_b": model_b,
        "winner": winner,
        "score_a": {"accuracy": score_a_accuracy, "fluency": score_a_fluency},
        "score_b": {"accuracy": score_b_accuracy, "fluency": score_b_fluency},
        "timestamp": timestamp,
        "cli_version": cli_version,
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def update_model_elos(model_a: str, model_b: str, winner: str) -> tuple[float, float]:
    """Update Elo ratings for two models after a judgment.

    Args:
        model_a: Name of model A.
        model_b: Name of model B.
        winner: "a", "b", or "tie".

    Returns:
        Tuple of (new_rating_a, new_rating_b).

    Raises:
        ValueError: If winner is not 'a', 'b', or 'tie'.
    """
    if winner not in ("a", "b", "tie"):
        raise ValueError(f"Invalid winner '{winner}'. Must be 'a', 'b', or 'tie'.")

    ratings = load_elo_ratings()
    rating_a = ratings.get(model_a, DEFAULT_RATING)
    rating_b = ratings.get(model_b, DEFAULT_RATING)

    new_a, new_b = update_elo(rating_a, rating_b, winner)
    ratings[model_a] = round(new_a, 1)
    ratings[model_b] = round(new_b, 1)

    save_elo_ratings(ratings)
    return ratings[model_a], ratings[model_b]
