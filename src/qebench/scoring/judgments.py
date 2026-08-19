"""Judgment results persistence — Elo ratings and judgment records.

Stores per-user judgment JSONL files and a shared elo.json.
"""

from __future__ import annotations

import json
from pathlib import Path

from qebench.scoring.elo import DEFAULT_RATING, update_elo
from qebench.utils.display import console

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
JUDGMENTS_DIR = _REPO_ROOT / "results" / "judgments"
ELO_PATH = _REPO_ROOT / "results" / "elo.json"


def load_elo_ratings() -> dict[str, float]:
    """Load model Elo ratings from elo.json.

    An unreadable or malformed file is reported and treated as absent, so
    ratings fall back to :data:`DEFAULT_RATING` rather than aborting a
    judging session.  ``UnicodeDecodeError`` is raised inside ``json.load``
    and subclasses ``ValueError``, so it is caught alongside ``OSError``
    and ``JSONDecodeError`` rather than by either of them.  A payload that
    parses but is not an object is dropped too — ``update_model_elos``
    calls ``.get`` on the result.

    Falling back is not free: nothing recomputes Elo from
    ``results/judgments/*.jsonl`` yet, so this file is the only record of
    the ratings and the next :func:`save_elo_ratings` would overwrite it.
    A file whose *contents* are bad is therefore moved aside first, so its
    bytes survive for repair — a misencoded file is one re-encode away
    from being readable again.

    A file we merely failed to *open* is left exactly where it is.  It may
    be perfectly good and only briefly locked, and renaming a healthy file
    out from under someone is worse than the fallback; if the condition
    persists, the save will fail to open it for writing too rather than
    overwrite it.

    Returns:
        Dict mapping model name to Elo rating.
    """
    if not ELO_PATH.exists():
        return {}
    try:
        with open(ELO_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except OSError as e:
        console.print(
            f"[yellow]warning:[/] cannot open {ELO_PATH.name} ({e}); "
            f"starting from default ratings, leaving the file untouched"
        )
        return {}
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        return _fall_back_preserving_cache(str(e))
    if not isinstance(data, dict):
        return _fall_back_preserving_cache("expected a JSON object of ratings")
    return data


def _fall_back_preserving_cache(reason: str) -> dict[str, float]:
    """Quarantine an unusable elo.json and start from default ratings."""
    quarantined = _quarantine_elo_file()
    detail = (
        f"kept the original at {quarantined.name}"
        if quarantined
        else "COULD NOT preserve the original"
    )
    console.print(
        f"[yellow]warning:[/] cannot use {ELO_PATH.name} ({reason}); "
        f"starting from default ratings and {detail}"
    )
    return {}


def _quarantine_elo_file() -> Path | None:
    """Move an unreadable elo.json aside so the next save cannot clobber it.

    Returns the path it was moved to, or None if it could not be moved —
    in which case the ratings really are about to be lost and the caller
    says so.
    """
    for suffix in ("corrupt", *(f"corrupt.{n}" for n in range(1, 100))):
        target = ELO_PATH.with_suffix(f".json.{suffix}")
        if target.exists():
            continue
        try:
            ELO_PATH.rename(target)
        except OSError:
            return None
        return target
    return None


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
    score_a_accuracy: int | None,
    score_a_fluency: int | None,
    score_b_accuracy: int | None,
    score_b_fluency: int | None,
    translation_a: str = "",
    translation_b: str = "",
    reference: str = "",
    domain: str = "",
    difficulty: str = "",
    suggestion: str = "",
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
        "translation_a": translation_a,
        "translation_b": translation_b,
        "reference": reference,
        "domain": domain,
        "difficulty": difficulty,
        "timestamp": timestamp,
        "cli_version": cli_version,
    }
    if suggestion:
        record["suggestion"] = suggestion
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def record_consensus(
    *,
    username: str,
    entry_id: str,
    models: list[str],
    translation: str,
    accuracy: int,
    fluency: int,
    reference: str = "",
    domain: str = "",
    difficulty: str = "",
    suggestion: str = "",
    timestamp: str,
    cli_version: str,
) -> None:
    """Append a consensus-rating record to the user's JSONL file."""
    if not 0 <= accuracy <= 5:
        raise ValueError("accuracy must be between 0 and 5")
    if not 0 <= fluency <= 5:
        raise ValueError("fluency must be between 0 and 5")
    JUDGMENTS_DIR.mkdir(parents=True, exist_ok=True)
    path = JUDGMENTS_DIR / f"{username}.jsonl"

    record = {
        "type": "consensus",
        "entry_id": entry_id,
        "models": models,
        "translation": translation,
        "accuracy": accuracy,
        "fluency": fluency,
        "reference": reference,
        "domain": domain,
        "difficulty": difficulty,
        "suggestion": suggestion,
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
        winner: "a", "b", "tie", or "neither".

    Returns:
        Tuple of (new_rating_a, new_rating_b).

    Raises:
        ValueError: If winner is not 'a', 'b', 'tie', or 'neither'.
    """
    if winner not in ("a", "b", "tie", "neither"):
        raise ValueError(f"Invalid winner '{winner}'. Must be 'a', 'b', 'tie', or 'neither'.")

    ratings = load_elo_ratings()
    rating_a = ratings.get(model_a, DEFAULT_RATING)
    rating_b = ratings.get(model_b, DEFAULT_RATING)

    # Treat "neither" as a tie for Elo calculation
    elo_winner = "tie" if winner == "neither" else winner
    new_a, new_b = update_elo(rating_a, rating_b, elo_winner)
    ratings[model_a] = round(new_a, 1)
    ratings[model_b] = round(new_b, 1)

    save_elo_ratings(ratings)
    return ratings[model_a], ratings[model_b]
