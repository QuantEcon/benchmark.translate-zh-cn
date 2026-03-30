"""Elo rating calculations for model comparison.

Standard Elo system: each model has a numeric rating. When two models
compete in a head-to-head human judgment, the winner gains points and
the loser loses points. The magnitude depends on the expected outcome.
"""

from __future__ import annotations

DEFAULT_K = 32  # K-factor: how much ratings change per match
DEFAULT_RATING = 1500  # Starting rating for new models


def expected_score(rating_a: float, rating_b: float) -> float:
    """Calculate expected score for player A given both ratings.

    Returns a value between 0 and 1, where 0.5 means equal strength.
    """
    return 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / 400.0))


def update_elo(
    rating_a: float,
    rating_b: float,
    winner: str,  # "a", "b", or "tie"
    k: float = DEFAULT_K,
) -> tuple[float, float]:
    """Update Elo ratings after a head-to-head comparison.

    Args:
        rating_a: Current rating of model A.
        rating_b: Current rating of model B.
        winner: "a" if A wins, "b" if B wins, "tie" for a draw.
        k: K-factor controlling rating volatility.

    Returns:
        Tuple of (new_rating_a, new_rating_b).
    """
    ea = expected_score(rating_a, rating_b)
    eb = 1.0 - ea

    if winner == "a":
        sa, sb = 1.0, 0.0
    elif winner == "b":
        sa, sb = 0.0, 1.0
    else:  # tie
        sa, sb = 0.5, 0.5

    new_a = rating_a + k * (sa - ea)
    new_b = rating_b + k * (sb - eb)
    return new_a, new_b
