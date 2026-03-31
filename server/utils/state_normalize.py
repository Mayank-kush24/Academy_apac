"""
State/province normalization for UserPII.state (app layer; DB unchanged).
Aliases are loaded from state_aliases.json (canonical name -> list of raw variants).
"""
from __future__ import annotations

import json
import os
from collections import defaultdict
from typing import Any, Iterable, Sequence

_DATA_PATH = os.path.join(os.path.dirname(__file__), "state_aliases.json")

with open(_DATA_PATH, encoding="utf-8") as _f:
    CANONICAL_STATE_ALIASES: dict[str, list[str]] = json.load(_f)

_REVERSE: dict[str, str] = {}
for _canonical, _aliases in CANONICAL_STATE_ALIASES.items():
    for _a in _aliases:
        if _a and str(_a).strip():
            _k = str(_a).strip().lower()
            if _k not in _REVERSE:
                _REVERSE[_k] = _canonical
    _ck = str(_canonical).strip().lower()
    if _ck not in _REVERSE:
        _REVERSE[_ck] = _canonical


def normalize_state(state: Any) -> str:
    """Return canonical state/province for display; unknown values returned trimmed."""
    if state is None:
        return ""
    if not isinstance(state, str):
        return state or ""
    s = state.strip()
    if not s:
        return ""
    return _REVERSE.get(s.lower(), s)


def get_state_filter_values(canonical: Any) -> list[str]:
    """
    DB values to match when filtering by a canonical state (for SQL IN (...)).
    Includes the canonical string and all listed aliases.
    """
    if not canonical or not isinstance(canonical, str):
        return []
    c = canonical.strip()
    aliases = CANONICAL_STATE_ALIASES.get(c)
    if not aliases:
        return [c]
    out = {str(x).strip() for x in aliases if x and str(x).strip()}
    out.add(c)
    return list(out)


def distinct_canonical_states(raw_states: Iterable[str | None]) -> list[str]:
    """Sorted unique canonical names for a list of raw DB values."""
    if not raw_states:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for s in raw_states:
        if not s:
            continue
        c = normalize_state(s)
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    out.sort(key=lambda x: x.lower())
    return out


def merge_state_count_rows(rows: Sequence[tuple[Any, int]]) -> list[tuple[str, int]]:
    """Merge (raw_state, count) by canonical label; sort by count desc."""
    merged: dict[str, int] = defaultdict(int)
    for raw, cnt in rows:
        label = normalize_state(raw) if raw else ""
        if not label:
            label = (str(raw).strip() if raw is not None else "") or "Unknown"
        merged[label] += int(cnt or 0)
    return sorted(merged.items(), key=lambda x: (-x[1], x[0].lower()))
