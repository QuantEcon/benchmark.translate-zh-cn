"""En/zh alignment checking for seeded sentence and paragraph entries.

A misaligned reference is worse than a missing one.  ``qebench judge`` scores
every judgment's ``reference_overlap`` against ``entry.zh`` and stores that
reference on the judgment record, so a `zh` that is not a translation of its
`en` quietly teaches judges from the wrong text.

Eight entries were seeded that way (#31), because the seeder accepted a pair
as soon as it shared any single math span — an English table and an unrelated
Chinese sentence both containing ``$x_1$`` passed.  This module is the single
definition of what makes a pair sound, used by three callers so they cannot
drift apart:

- ``scripts/seed_from_lectures.py`` refuses to seed a pair this rejects, so
  new data passes the audit by construction
- ``scripts/audit_alignment.py`` reports on the committed dataset
- ``qebench validate`` surfaces regressions in CI

The signals are the ones that must survive a faithful translation:

- **Math spans** — ``$...$`` content is copied verbatim, never translated,
  so most of the source's math should reappear in the reference.
- **Reference targets** — the target of a ``{doc}``/``{eq}``/``{ref}`` role
  is an identifier.  Display text is translated; the target is not.
- **Length ratio** — the weakest signal, and used as such: English is often
  simply more verbose than its translation.
"""

from __future__ import annotations

import re

# Chinese renders English in roughly 0.4-0.6 of the characters; well below
# that means the reference is not a translation of the whole source.
MIN_LENGTH_RATIO = 0.30

# The bar when every math span and reference target carried over.  That is
# direct evidence the pair corresponds, so verbose English is tolerated —
# but not a translation that keeps a marker and drops the prose around it.
MIN_LENGTH_RATIO_SUPPORTED = 0.20

# Fraction of the source's math spans that may go missing before the pair is
# treated as misaligned rather than merely reformatted.
MAX_MISSING_MATH = 0.5

_MATH = re.compile(r"\$[^$\n]+\$")
_ROLE = re.compile(r"\{(eq|doc|ref|numref|cite|any|term)\}`([^`]*)`")
_ROLE_TARGET = re.compile(r"<([^>]+)>\s*$")

# Inline math or a MyST role — the markers a pair is scored on.  Text with
# none of them can only be judged on length.
HAS_MARKERS = re.compile(r"\$[^$\n]+\$|\{(?:eq|doc|ref|numref|cite|any|term)\}`")


def math_spans(text: str) -> set[str]:
    """Inline math spans, which a faithful translation copies verbatim."""
    return set(_MATH.findall(text))


def role_targets(text: str) -> set[tuple[str, str]]:
    """(role name, link target) pairs.

    For ``{doc}`display text <target>``` the target is the identifier; for a
    bare ``{eq}`label``` the whole body is the identifier.  Display text is
    expected to be translated, so it is deliberately excluded.
    """
    targets: set[tuple[str, str]] = set()
    for name, body in _ROLE.findall(text):
        match = _ROLE_TARGET.search(body)
        targets.add((name, match.group(1).strip() if match else body.strip()))
    return targets


def check_pair(en: str, zh: str) -> list[str]:
    """Return a list of alignment problems, empty when the pair looks sound."""
    problems: list[str] = []

    en_math = math_spans(en)
    missing_math: set[str] = set()
    if en_math:
        missing_math = en_math - math_spans(zh)
        if len(missing_math) / len(en_math) > MAX_MISSING_MATH:
            problems.append(f"{len(missing_math)}/{len(en_math)} math spans missing")

    en_roles = role_targets(en)
    missing_roles: set[tuple[str, str]] = set()
    if en_roles:
        missing_roles = en_roles - role_targets(zh)
        if missing_roles:
            names = ", ".join(sorted(f"{{{n}}}`{t}`" for n, t in missing_roles))
            problems.append(f"{len(missing_roles)}/{len(en_roles)} reference targets missing: {names}")

    # Length is the weakest of the three signals — English is often simply
    # more verbose than its translation.  When the pair carries markers and
    # every one survives, that is direct evidence of correspondence, so the
    # bar drops rather than disappearing: a pair that keeps its one math span
    # while dropping nine tenths of its prose is still worth flagging.
    has_markers = bool(en_math or en_roles)
    supported = has_markers and not missing_math and not missing_roles
    floor = MIN_LENGTH_RATIO_SUPPORTED if supported else MIN_LENGTH_RATIO
    ratio = len(zh) / max(len(en), 1)
    if ratio < floor:
        problems.append(f"length ratio {ratio:.2f} (expected >= {floor})")

    return problems
