"""XP scoring — track contribution points per user.

Actions earn XP:
  - translate: 10 XP per entry completed
  - add:       15 XP per entry contributed
  - judge:      5 XP per judgment made
"""

from __future__ import annotations

import json
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
XP_DIR = _REPO_ROOT / "results" / "xp"

# XP awarded per action per item
XP_TRANSLATE = 10
XP_ADD = 15
XP_JUDGE = 5

_XP_VALUES = {
    "translate": XP_TRANSLATE,
    "add": XP_ADD,
    "judge": XP_JUDGE,
}


def _xp_path(username: str) -> Path:
    return XP_DIR / f"{username}.json"


def load_xp(username: str) -> int:
    """Load total XP for a user."""
    path = _xp_path(username)
    if not path.exists():
        return 0
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("total", 0)


def load_xp_details(username: str) -> dict:
    """Load full XP breakdown for a user."""
    path = _xp_path(username)
    if not path.exists():
        return {"total": 0, "actions": {}}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def award_xp(username: str, action: str, count: int = 1) -> int:
    """Award XP for an action and persist to disk.

    Returns the amount of XP awarded.
    """
    per_item = _XP_VALUES.get(action, 0)
    earned = per_item * count

    if earned == 0:
        return 0

    XP_DIR.mkdir(parents=True, exist_ok=True)
    path = _xp_path(username)

    data: dict = {"total": 0, "actions": {}}
    if path.exists():
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

    data["total"] = data.get("total", 0) + earned
    actions = data.get("actions", {})
    actions[action] = actions.get(action, 0) + earned
    data["actions"] = actions

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")

    return earned
