"""XP scoring — track contribution points per user.

Actions earn XP:
  - translate: 10 XP per entry completed
  - add:       15 XP per entry contributed
  - judge:      5 XP per judgment made
"""

from __future__ import annotations

import json
from pathlib import Path

from qebench.utils.display import console

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


def _read_xp_file(path: Path) -> dict | None:
    """Read one XP file, or return ``None`` if it cannot be used.

    Contributors hand-edit these files on their own machines, so a truncated
    save or one written in GBK rather than UTF-8 is a realistic failure in a
    zh-cn repo.  ``UnicodeDecodeError`` is raised inside ``json.load`` and
    subclasses ``ValueError`` — it is neither an ``OSError`` nor a
    ``JSONDecodeError`` — so all three have to be caught, as does a payload
    that parses but is not an object.
    """
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        console.print(f"[yellow]warning:[/] cannot read XP file {path.name}: {e}")
        return None
    if not isinstance(data, dict):
        console.print(f"[yellow]warning:[/] ignoring XP file {path.name}: expected a JSON object")
        return None
    # A hand-edit can leave a well-formed object with a wrong-typed field —
    # {"total": null} or {"actions": null}.  Those parse, so the checks above
    # pass, but they blow up in award_xp's arithmetic (TypeError) and in
    # actions.get (AttributeError), which is the crash this guard exists to
    # prevent.  Reject them here so award_xp declines instead of clobbering.
    if not isinstance(data.get("total", 0), (int, float)) or not isinstance(
        data.get("actions", {}), dict
    ):
        console.print(
            f"[yellow]warning:[/] ignoring XP file {path.name}: "
            f"'total' must be a number and 'actions' an object"
        )
        return None
    return data


def load_xp(username: str) -> int:
    """Load total XP for a user.

    An unreadable file is reported and treated as no XP, so one bad file
    cannot take down a display that shows every user's score.
    """
    path = _xp_path(username)
    if not path.exists():
        return 0
    data = _read_xp_file(path)
    if data is None:
        return 0
    return data.get("total", 0)


def load_xp_details(username: str) -> dict:
    """Load full XP breakdown for a user.

    An unreadable file is reported and falls back to an empty breakdown.
    """
    path = _xp_path(username)
    if not path.exists():
        return {"total": 0, "actions": {}}
    data = _read_xp_file(path)
    if data is None:
        return {"total": 0, "actions": {}}
    return data


def award_xp(username: str, action: str, count: int = 1) -> int:
    """Award XP for an action and persist to disk.

    Returns the amount of XP awarded.

    If the user already has an XP file that cannot be read, the award is
    skipped and 0 is returned rather than starting again from zero: the file
    is the only record of the total, so writing over it would destroy it.
    Awarding nothing is recoverable once the file is repaired; clobbering a
    total is not.  Callers already handle a 0 return — it is what an unknown
    action gives.
    """
    per_item = _XP_VALUES.get(action, 0)
    earned = per_item * count

    if earned == 0:
        return 0

    XP_DIR.mkdir(parents=True, exist_ok=True)
    path = _xp_path(username)

    data: dict = {"total": 0, "actions": {}}
    if path.exists():
        existing = _read_xp_file(path)
        if existing is None:
            console.print(
                f"[yellow]warning:[/] not awarding {earned} XP to {username} — "
                f"overwriting {path.name} would erase the stored total; "
                f"repair the file and re-run."
            )
            return 0
        data = existing

    data["total"] = data.get("total", 0) + earned
    actions = data.get("actions", {})
    actions[action] = actions.get(action, 0) + earned
    data["actions"] = actions

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")

    return earned
