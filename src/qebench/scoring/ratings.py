"""Recompute model ratings from the committed judgment logs.

``results/elo.json`` is gitignored and was only ever written incrementally by
whoever happened to be judging, so ratings lived on one machine and never
reached the dashboard.  The judgment logs under ``results/judgments/`` are
committed, so they — not the cache — are the source of truth.  This module
rebuilds the ratings from them, which makes the numbers reproducible, lets CI
compute them, and means a lost or corrupt cache costs nothing.

Three things about the recorded data need handling, all visible in the 21
judgments that exist today:

**Mixed label granularity.** Early records name a bare ``model``;
``model:prompt`` labelling arrived in v0.4.0 (PR #22), and judge.py still
writes a bare label for any model output with no ``prompt_template``.  A
bare label cannot be attributed to a prompt after the fact, so ratings are
computed at two granularities rather than guessing:

- ``by_prompt=True`` ranks ``model:prompt`` labels, using only records where
  both sides carry a prompt.
- ``by_prompt=False`` strips prompts, which lets bare-labelled records count
  — but it also collapses a record pitting two prompts of one model onto a
  single competitor, and those are dropped rather than rating a model
  against itself.

Neither is a superset of the other, and on today's log the coarse ranking
rests on *less* evidence: 7 rated matches against 10.  Quote ``by_model``
for model selection, but read the match counts with it.

**Two score scales.** Scores do not enter Elo — only the winner does — but
they do enter the score summary, and they changed from 1-10 to 0-5 in v0.4.0.
Which scale a record used is decided from the record's own scores first and
its ``cli_version`` only as a fallback, because the stamp is not reliable:
it records the last *released* version, not the code that was running. The
proof is in this repo's own log — three ``type: "consensus"`` records are
stamped ``0.3.1``, but consensus shipped in v0.4.0, so they were written by
pre-release code. Trusting the stamp there would rescale a modern 5 to 2.22.
See :func:`record_scale_max`.

**Judgments against the human reference.** ``qebench judge`` deliberately
skips Elo when one side is ``human-reference``, since the reference is not a
competitor.  The recompute excludes them for the same reason; today that is 5
of the 17 pairwise records.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from rich.markup import escape

from qebench.scoring.elo import DEFAULT_RATING, update_elo
from qebench.utils.display import console

# The label judge.py gives the dataset's own translation. Not a competitor.
HUMAN_REFERENCE = "human-reference"

# The 0-5 scale shipped in v0.4.0 (PR #23); before that judge.py offered
# `range(1, 11)` and prompted for "Accuracy (1-10)".
_ZERO_TO_FIVE_FROM = (0, 4, 0)

_OLD_SCALE_MIN, _OLD_SCALE_MAX = 1, 10
_NEW_SCALE_MAX = 5


@dataclass(frozen=True)
class Rating:
    """One competitor's rating and record."""

    label: str
    rating: float
    matches: int
    wins: int
    losses: int
    ties: int

    def as_dict(self) -> dict:
        return {
            "label": self.label,
            "rating": round(self.rating, 1),
            "matches": self.matches,
            "wins": self.wins,
            "losses": self.losses,
            "ties": self.ties,
        }


def parse_version(cli_version: str) -> tuple[int, int, int]:
    """Parse ``"0.3.1"`` into ``(0, 3, 1)``, tolerating junk.

    Always three components, so ``"0.4"`` compares as ``(0, 4, 0)`` rather
    than sorting below it.  An unparseable version becomes ``(0, 0, 0)``,
    i.e. oldest.  Only leading decimal digits of a chunk count, so a
    pre-release suffix like ``"0.4.0rc1"`` reads as ``(0, 4, 0)``.
    """
    parts: list[int] = []
    for chunk in str(cli_version).split("."):
        digits = ""
        for char in chunk:
            if not char.isdecimal():
                break
            digits += char
        if not digits:
            break
        parts.append(int(digits))
    while len(parts) < 3:
        parts.append(0)
    return (parts[0], parts[1], parts[2])


def _numeric_scores(record: dict) -> list[float]:
    """Every accuracy/fluency value on a record, whatever its shape."""
    values: list[float] = []
    candidates = [record.get("accuracy"), record.get("fluency")]
    for side in ("a", "b"):
        scores = record.get(f"score_{side}")
        if isinstance(scores, dict):
            candidates.extend([scores.get("accuracy"), scores.get("fluency")])
    for value in candidates:
        if not isinstance(value, bool) and isinstance(value, (int, float)):
            values.append(float(value))
    return values


def record_scale_max(record: dict) -> int:
    """Whether this record's scores are on the 1-10 or the 0-5 scale.

    The record's own scores decide it wherever they can, because
    ``cli_version`` stamps the last released version rather than the code
    that ran — this repo's log already contains v0.4.0-only consensus
    records stamped ``0.3.1``.  A score above 5 is impossible on the new
    scale and a 0 is impossible on the old one, so either is conclusive.

    Only when the scores are all in 1-5, where the scales overlap and no
    evidence exists, does the version stamp break the tie.  Reading an
    ambiguous legacy 3 as a 3 rather than a 1.11 is the safer error: it
    stays in range, and it cannot manufacture a score the judge never gave.
    """
    scores = _numeric_scores(record)
    if any(value > _NEW_SCALE_MAX for value in scores):
        return _OLD_SCALE_MAX
    if any(value == 0 for value in scores):
        return _NEW_SCALE_MAX
    # A consensus record can only have been written by v0.4.0 or later — it
    # shipped in the same PR as the 0-5 scale.  That is stronger evidence
    # than the stamp, and it matters: this log's consensus records are
    # stamped 0.3.1 and score 5, which the stamp alone would rescale to 2.22.
    if record.get("type") == "consensus":
        return _NEW_SCALE_MAX
    if parse_version(record.get("cli_version", "")) >= _ZERO_TO_FIVE_FROM:
        return _NEW_SCALE_MAX
    return _OLD_SCALE_MAX


def normalise_score(value: object, scale_max: int) -> float | None:
    """Put one accuracy or fluency score on the 0-5 scale.

    *scale_max* comes from :func:`record_scale_max`.  Returns None for a
    missing or non-numeric score — judge.py records None on both sides when
    the verdict is "neither", and that is an absence, not a zero.

    The result is clamped to 0-5.  Without that a malformed record could
    publish a negative accuracy, or a 9 in a column the dashboard labels
    0-5.
    """
    if scale_max not in (_NEW_SCALE_MAX, _OLD_SCALE_MAX):
        # This argument used to be a cli_version string. Passing one now
        # would compare unequal to both scales and silently take the legacy
        # branch, rescaling every modern score, so refuse it outright.
        raise ValueError(
            f"scale_max must be {_NEW_SCALE_MAX} or {_OLD_SCALE_MAX}, "
            f"got {scale_max!r} — use record_scale_max(record)"
        )
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if scale_max == _NEW_SCALE_MAX:
        scaled = float(value)
    else:
        # Map 1-10 onto 0-5 by position in the range, so 1 -> 0 and 10 -> 5.
        span = _OLD_SCALE_MAX - _OLD_SCALE_MIN
        scaled = (float(value) - _OLD_SCALE_MIN) / span * _NEW_SCALE_MAX
    return max(0.0, min(float(_NEW_SCALE_MAX), scaled))


def strip_prompt(label: str) -> str:
    """``"claude-sonnet-4-6:academic"`` -> ``"claude-sonnet-4-6"``."""
    return label.split(":", 1)[0]


def load_judgment_records(directory: Path) -> list[dict]:
    """Load every judgment record, in a deterministic order.

    Elo is path dependent, so the order has to be stable across machines or
    the same logs would produce different ratings.  Records sort by
    timestamp, then username, then position in the file — the last two break
    ties between records written in the same instant by different people.

    Unreadable files and malformed lines are reported and skipped rather than
    aborting, matching the other readers in this codebase.
    """
    records: list[dict] = []
    if not directory.exists():
        return records

    for path in sorted(directory.glob("*.jsonl")):
        username = path.stem
        lineno = 0
        try:
            with open(path, encoding="utf-8-sig") as f:
                for lineno, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError as e:
                        console.print(
                            f"[yellow]warning:[/] skipping malformed line {lineno} in {escape(path.name)}: {e}"
                        )
                        continue
                    if not isinstance(record, dict):
                        console.print(
                            f"[yellow]warning:[/] skipping non-object record on line "
                            f"{lineno} in {escape(path.name)}"
                        )
                        continue
                    record["username"] = username
                    record["_lineno"] = lineno
                    records.append(record)
        except (OSError, UnicodeDecodeError) as e:
            console.print(
                f"[yellow]warning:[/] {escape(path.name)} unreadable after {lineno} line(s), "
                f"skipping the rest: {e}"
            )
            continue

    records.sort(key=_replay_order)
    return records


def _replay_order(record: dict) -> tuple[str, str, int]:
    """Sort key for the replay.

    A non-string timestamp is treated as absent rather than stringified: a
    JSON null would otherwise become ``"None"``, which sorts after every
    ``"2026-..."`` date, while a missing key sorts before them — the same
    condition landing at opposite ends of a path-dependent replay.
    """
    timestamp = record.get("timestamp")
    return (
        timestamp if isinstance(timestamp, str) else "",
        record.get("username", ""),
        record.get("_lineno", 0),
    )


def _competitors(record: dict, *, by_prompt: bool | None) -> tuple[str, str]:
    """The two competitor labels this record rates at the given granularity."""
    label_a, label_b = record["model_a"], record["model_b"]
    if by_prompt is False:
        return strip_prompt(label_a), strip_prompt(label_b)
    return label_a, label_b


def _same_competitor(record: dict, *, by_prompt: bool | None) -> bool:
    """Whether both sides resolve to one competitor at this granularity."""
    label_a, label_b = _competitors(record, by_prompt=by_prompt)
    return label_a == label_b


def elo_eligible(record: dict, *, by_prompt: bool | None) -> bool:
    """Whether a record is a head-to-head between two rateable competitors.

    *by_prompt* selects the granularity: True ranks ``model:prompt`` and
    needs a prompt on both sides, False strips prompts, and None takes the
    labels exactly as recorded — which is what the local elo.json cache
    needs, since judge.py keys it on whatever label it wrote.
    """
    if record.get("type") == "consensus":
        return False
    label_a, label_b = record.get("model_a"), record.get("model_b")
    if not isinstance(label_a, str) or not isinstance(label_b, str):
        return False
    if HUMAN_REFERENCE in (label_a, label_b):
        return False
    if record.get("winner") not in ("a", "b", "tie", "neither"):
        return False
    if by_prompt is True and (":" not in label_a or ":" not in label_b):
        return False
    # Two prompts of one model collapse to a single competitor once prompts
    # are stripped.  recompute_elo skips those, so counting them as eligible
    # would overstate the evidence behind the by-model ranking — on today's
    # log that reported 12 matches for a table built from 7.
    return not _same_competitor(record, by_prompt=by_prompt)


def recompute_elo(records: list[dict], *, by_prompt: bool | None = True) -> list[Rating]:
    """Replay every eligible judgment to produce ratings, highest first.

    *records* must already be in a deterministic order — use
    :func:`load_judgment_records`.
    """
    ratings: dict[str, float] = {}
    tally: dict[str, dict[str, int]] = {}

    def _tally(label: str) -> dict[str, int]:
        return tally.setdefault(label, {"matches": 0, "wins": 0, "losses": 0, "ties": 0})

    for record in records:
        if not elo_eligible(record, by_prompt=by_prompt):
            continue
        label_a, label_b = _competitors(record, by_prompt=by_prompt)
        winner = record["winner"]
        # judge.py treats "neither" as a tie for rating purposes.
        elo_winner = "tie" if winner == "neither" else winner

        new_a, new_b = update_elo(
            ratings.get(label_a, DEFAULT_RATING),
            ratings.get(label_b, DEFAULT_RATING),
            elo_winner,
        )
        ratings[label_a], ratings[label_b] = new_a, new_b

        ta, tb = _tally(label_a), _tally(label_b)
        ta["matches"] += 1
        tb["matches"] += 1
        if elo_winner == "a":
            ta["wins"] += 1
            tb["losses"] += 1
        elif elo_winner == "b":
            tb["wins"] += 1
            ta["losses"] += 1
        else:
            ta["ties"] += 1
            tb["ties"] += 1

    return sorted(
        (Rating(label=label, rating=rating, **tally[label]) for label, rating in ratings.items()),
        key=lambda r: (-r.rating, r.label),
    )


def score_summary(records: list[dict], *, by_prompt: bool = True) -> dict[str, dict]:
    """Mean accuracy and fluency per competitor, on the 0-5 scale.

    Consensus records rate a single translation that several models agreed
    on, so their score is credited to every model named on the record.
    """
    totals: dict[str, dict[str, list[float]]] = {}

    def _resolve(label: object) -> str | None:
        """The competitor this label counts towards, or None to skip it."""
        if not isinstance(label, str) or label == HUMAN_REFERENCE:
            return None
        if by_prompt:
            return label if ":" in label else None
        return strip_prompt(label)

    def _credit(
        into: dict[str, dict[str, list[float]]],
        key: str,
        accuracy: float | None,
        fluency: float | None,
    ) -> None:
        bucket = into.setdefault(key, {"accuracy": [], "fluency": []})
        if accuracy is not None:
            bucket["accuracy"].append(accuracy)
        if fluency is not None:
            bucket["fluency"].append(fluency)

    for record in records:
        scale_max = record_scale_max(record)

        if record.get("type") == "consensus":
            # One translation, rated once, that several models produced
            # identically. Each distinct model earns that rating — but only
            # once: a consensus naming two prompts of the same model
            # collapses to one key under by_prompt=False, and crediting it
            # twice would let a single human rating vote twice for that
            # model's mean and inflate its `rated` count.
            accuracy = normalise_score(record.get("accuracy"), scale_max)
            fluency = normalise_score(record.get("fluency"), scale_max)
            models = record.get("models")
            if not isinstance(models, list):
                continue
            seen: set[str] = set()
            for label in models:
                key = _resolve(label)
                if key is None or key in seen:
                    continue
                seen.add(key)
                _credit(totals, key, accuracy, fluency)
            continue

        # A pairwise record holds two *different* translations, each with
        # its own score. Both count even when they resolve to the same
        # competitor — two prompts of one model are still two rated outputs.
        for side in ("a", "b"):
            key = _resolve(record.get(f"model_{side}"))
            scores = record.get(f"score_{side}")
            if key is None or not isinstance(scores, dict):
                continue
            _credit(
                totals,
                key,
                normalise_score(scores.get("accuracy"), scale_max),
                normalise_score(scores.get("fluency"), scale_max),
            )

    summary: dict[str, dict] = {}
    for label, bucket in totals.items():
        accuracy, fluency = bucket["accuracy"], bucket["fluency"]
        if not accuracy and not fluency:
            continue
        summary[label] = {
            "accuracy": round(sum(accuracy) / len(accuracy), 2) if accuracy else None,
            "fluency": round(sum(fluency) / len(fluency), 2) if fluency else None,
            "rated": max(len(accuracy), len(fluency)),
        }
    return summary
