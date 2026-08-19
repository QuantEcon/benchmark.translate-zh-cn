"""Judgment results persistence — Elo ratings and judgment records.

Stores per-user judgment JSONL files and a local elo.json.  The JSONL files
are committed and authoritative; elo.json is a gitignored cache of the
ratings they imply, and :mod:`qebench.scoring.ratings` can rebuild it from
them whenever it goes missing or bad.
"""

from __future__ import annotations

import json
from pathlib import Path

from qebench.scoring.elo import DEFAULT_RATING, update_elo
from qebench.scoring.ratings import load_judgment_records, recompute_elo
from qebench.utils.display import console

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
JUDGMENTS_DIR = _REPO_ROOT / "results" / "judgments"
ELO_PATH = _REPO_ROOT / "results" / "elo.json"


def load_elo_ratings() -> dict[str, float]:
    """Load model Elo ratings from elo.json, rebuilding it when unusable.

    elo.json is a gitignored local cache; the judgment logs under
    ``results/judgments/`` are committed and are the source of truth.  So a
    missing, unreadable or malformed cache costs nothing but time: the
    ratings are rebuilt from the logs by :func:`_rebuild_from_judgments`
    rather than everyone restarting from :data:`DEFAULT_RATING`.
    ``UnicodeDecodeError`` is raised inside ``json.load`` and subclasses
    ``ValueError``, so it is caught alongside ``OSError`` and
    ``JSONDecodeError`` rather than by either of them.  A payload that
    parses but is not an object is dropped too — ``update_model_elos``
    calls ``.get`` on the result.

    A file whose *contents* are bad is still moved aside before the rebuild.
    The rebuild makes its ratings recoverable, but the file itself is not:
    it may hold a hand-edit or a label the logs no longer mention, and a
    misencoded file is one re-encode away from being readable again.
    Quarantining costs nothing and stops the next :func:`save_elo_ratings`
    silently overwriting it.

    A file we merely failed to *open* is left exactly where it is.  It may
    be perfectly good and only briefly locked, and renaming a healthy file
    out from under someone is worse than the rebuild; if the condition
    persists, the save will fail to open it for writing too rather than
    overwrite it.

    Cost: a rebuild reads every judgment log, and ``update_model_elos``
    calls this once per judgment.  Each call rebuilds at most once, and the
    healthy path — a readable cache — never touches the logs at all.  The
    result is deliberately not cached between calls: a judging session
    appends to the logs as it goes, so a process-wide cache would go stale
    within the session.

    Returns:
        Dict mapping model name to Elo rating.
    """
    if not ELO_PATH.exists():
        return _rebuild_from_judgments()
    try:
        with open(ELO_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except OSError as e:
        console.print(
            f"[yellow]warning:[/] cannot open {ELO_PATH.name} ({e}); "
            f"rebuilding ratings from the judgment logs, leaving the file untouched"
        )
        return _rebuild_from_judgments()
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        return _quarantine_and_rebuild(str(e))
    if not isinstance(data, dict):
        return _quarantine_and_rebuild("expected a JSON object of ratings")
    # The container being right does not make the values usable: a
    # hand-edited {"claude": "1700"} parses fine, then update_elo does
    # arithmetic on it and raises TypeError.  bool is excluded because it
    # subclasses int and a True rating is a corruption, not a 1.
    bad = [
        model
        for model, rating in data.items()
        if isinstance(rating, bool) or not isinstance(rating, (int, float))
    ]
    if bad:
        return _quarantine_and_rebuild(
            f"non-numeric rating for {', '.join(sorted(bad))}"
        )
    return data


def _rebuild_from_judgments() -> dict[str, float]:
    """Replay the committed judgment logs into ``{label: rating}``.

    Rates labels exactly as recorded (``by_prompt=None``), because this
    cache is keyed on whatever label ``qebench judge`` wrote.  Ranking
    ``model:prompt`` here instead would drop every judgment carrying a bare
    label — and judge.py still emits one for any model output with no
    ``prompt_template`` — so on such a dataset the rebuild would return
    ``{}`` and everyone would silently restart at :data:`DEFAULT_RATING`,
    which is the failure this fallback exists to prevent.

    One consequence a caller has to know about, because a rebuilt cache is
    *not* the cache the incremental path would have produced:

    * Ratings are rounded once, at the end, to the one decimal place
      :func:`update_model_elos` stores.  That path instead rounds after
      *every* judgment and feeds the rounded value into the next expected
      score, so the two replays drift: on the logs committed today they
      differ by 0.1 for two of the five labels, and the gap grows with the
      number of judgments.

    Reads every ``*.jsonl`` under :data:`JUDGMENTS_DIR` — the whole cost of
    the fallback lives here, so call it once per :func:`load_elo_ratings`.
    An absent directory yields no records and therefore no ratings, which
    is the correct answer for a checkout nobody has judged in yet.
    """
    records = load_judgment_records(JUDGMENTS_DIR)
    return {r.label: round(r.rating, 1) for r in recompute_elo(records, by_prompt=None)}


def _quarantine_and_rebuild(reason: str) -> dict[str, float]:
    """Move an unusable elo.json aside, then rebuild the ratings from the logs."""
    quarantined = _quarantine_elo_file()
    detail = (
        f"kept the original at {quarantined.name}"
        if quarantined
        else "could not move the original aside"
    )
    console.print(
        f"[yellow]warning:[/] cannot use {ELO_PATH.name} ({reason}); "
        f"rebuilding ratings from the judgment logs and {detail}"
    )
    return _rebuild_from_judgments()


def _quarantine_elo_file() -> Path | None:
    """Move an unreadable elo.json aside so the next save cannot clobber it.

    Returns the path it was moved to, or None if it could not be moved.
    The ratings survive either way — they are rebuilt from the judgment
    logs — but the file's own bytes only survive the move, so the caller
    says which happened.
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
