"""
Canonical country names and raw-value aliases. Normalize in the application layer only (DB unchanged).
Match is case-insensitive on SQL TRIM/LOWER equality to alias strings.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable, Sequence

# User-provided: canonical display name -> list of equivalent raw strings
CANONICAL_COUNTRY_ALIASES: dict[str, list[str]] = {
    "Afghanistan": ["Afghanistan"],
    "Argentina": ["Argentina"],
    "Australia": ["Australia"],
    "Austria": ["Austria"],
    "Bangladesh": ["Bangladesh"],
    "Belgium": ["Belgium"],
    "Bhutan": ["Bhutan"],
    "Brazil": ["Brazil"],
    "Brunei": ["Brunei"],
    "Cambodia": ["Cambodia"],
    "Canada": ["Canada"],
    "China": ["China"],
    "Estonia": ["Estonia"],
    "Finland": ["Finland"],
    "Germany": ["Germany"],
    "Hong Kong": ["Hong Kong", "Hong Kong S.A.R."],
    "India": ["India"],
    "Indonesia": ["Indonesia", "Republic of Indonesia", "INDONESIA"],
    "Iran": ["Iran"],
    "Ireland": ["Ireland"],
    "Israel": ["Israel"],
    "Japan": ["Japan"],
    "Laos": ["Laos"],
    "Lebanon": ["Lebanon"],
    "Malaysia": ["Malaysia"],
    "Moldova": ["Moldova"],
    "Myanmar": ["Myanmar"],
    "Nepal": ["Nepal"],
    "Netherlands": ["Netherlands"],
    "New Zealand": ["New Zealand"],
    "Norway": ["Norway"],
    "Pakistan": ["Pakistan", "PAKISTAN"],
    "Papua New Guinea": ["Papua New Guinea"],
    "Philippines": ["Philippines"],
    "Poland": ["Poland"],
    "Russia": ["Russia"],
    "Singapore": ["Singapore"],
    "South Africa": ["South Africa"],
    "South Korea": ["South Korea"],
    "Sri Lanka": ["Sri Lanka"],
    "Sweden": ["Sweden"],
    "Switzerland": ["Switzerland"],
    "Taiwan": ["Taiwan"],
    "Thailand": ["Thailand"],
    "Timor-Leste": ["Timor-Leste"],
    "United Arab Emirates": ["United Arab Emirates"],
    "United Kingdom": ["United Kingdom"],
    "United States": ["United States"],
    "Vietnam": ["Vietnam", "VIETNAM"],
}

# Used by dashboard region / APAC logic; not all were in the user map
CANONICAL_COUNTRY_ALIASES_EXTRA: dict[str, list[str]] = {
    "Mongolia": ["Mongolia"],
    "North Korea": ["North Korea"],
    "Fiji": ["Fiji"],
    "Maldives": ["Maldives"],
    "APAC": ["APAC", "Asia Pacific"],
}


def _merged_aliases() -> dict[str, list[str]]:
    out = dict(CANONICAL_COUNTRY_ALIASES)
    for k, v in CANONICAL_COUNTRY_ALIASES_EXTRA.items():
        out[k] = v
    return out


FULL_MAP: dict[str, list[str]] = _merged_aliases()

_REVERSE: dict[str, str] = {}
for _canonical, _aliases in FULL_MAP.items():
    for _a in _aliases:
        if _a and str(_a).strip():
            _REVERSE[str(_a).strip().lower()] = _canonical
    _REVERSE[_canonical.strip().lower()] = _canonical


def normalize_country(raw: Any) -> str | None:
    """Return canonical country name, or stripped original if unknown."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    return _REVERSE.get(s.lower(), s)


def distinct_canonical_countries(raw_values: Iterable[str | None]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for r in raw_values:
        if not r:
            continue
        c = normalize_country(r) or str(r).strip()
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    out.sort(key=lambda x: x.lower())
    return out


def merge_country_count_rows(rows: Sequence[tuple[Any, int]]) -> list[tuple[str, int]]:
    """Merge (raw_country, count) by normalized label; sort by count desc then name."""
    merged: dict[str, int] = defaultdict(int)
    for raw, cnt in rows:
        label = normalize_country(raw)
        if not label:
            label = (str(raw).strip() if raw is not None else "") or "Unknown"
        merged[label] += int(cnt or 0)
    return sorted(merged.items(), key=lambda x: (-x[1], x[0].lower()))


def _alias_tuple_for_canonical(canonical: str) -> tuple[str, ...]:
    aliases = FULL_MAP.get(canonical)
    if not aliases:
        aliases = [canonical]
    return tuple({a.strip().lower() for a in aliases if a and str(a).strip()})


def country_column_matches_canonical(column, canonical: str):
    """SQL: trimmed lower(country) equals one of the known aliases for canonical."""
    from sqlalchemy import func

    tup = _alias_tuple_for_canonical(canonical)
    if not tup:
        return column == canonical
    return func.lower(func.trim(column)).in_(tup)


def country_column_matches_any_canonical(column, canonical_names: Sequence[str]):
    from sqlalchemy import or_

    parts = [country_column_matches_canonical(column, c) for c in canonical_names if c]
    if not parts:
        return None
    return or_(*parts)


def country_filter_or_conditions(column, selected_values: Sequence[str]):
    """
    OR of filters for multi-select. Resolved canonicals use exact alias set; unknown values use ILIKE.
    """
    from sqlalchemy import or_

    parts = []
    for c in selected_values:
        if not (c and str(c).strip()):
            continue
        c = str(c).strip()
        if c in FULL_MAP:
            parts.append(country_column_matches_canonical(column, c))
            continue
        resolved = normalize_country(c)
        if resolved and resolved in FULL_MAP:
            parts.append(country_column_matches_canonical(column, resolved))
        else:
            parts.append(column.ilike(f"%{c}%"))
    if not parts:
        return None
    return or_(*parts)
