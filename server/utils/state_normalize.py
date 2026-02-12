"""
State spelling normalization for UserPII.state (India and others).
Maps common misspellings to the canonical form (the one with most registrations).
Add new mappings here as more misspellings are found.
"""
# variant -> canonical (canonical = preferred display spelling)
STATE_MAPPING = {
    'Uttar Preadesh': 'Uttar Pradesh',
    'UTTAR PRADESH': 'Uttar Pradesh',
    'Telengana': 'Telangana',
    'Tamilnadu': 'Tamil Nadu',
}

# Reverse: canonical -> list of all variants (including canonical) for filtering
_canonical_to_variants = None


def _build_reverse():
    global _canonical_to_variants
    if _canonical_to_variants is not None:
        return
    _canonical_to_variants = {}
    for variant, canonical in STATE_MAPPING.items():
        if canonical not in _canonical_to_variants:
            _canonical_to_variants[canonical] = [canonical]
        if variant not in _canonical_to_variants[canonical]:
            _canonical_to_variants[canonical].append(variant)


def normalize_state(state):
    """Return canonical state name for display. If not in mapping, return state unchanged."""
    if not state or not isinstance(state, str):
        return state or ''
    s = state.strip()
    return STATE_MAPPING.get(s, s)


def get_state_filter_values(canonical):
    """
    Return list of state strings to match when filtering by this canonical name.
    Includes the canonical and all variants that map to it.
    Use with: query.filter(UserPII.state.in_(get_state_filter_values(selected)))
    """
    if not canonical or not isinstance(canonical, str):
        return []
    _build_reverse()
    c = canonical.strip()
    if c in _canonical_to_variants:
        return _canonical_to_variants[c]
    return [c]


def distinct_canonical_states(raw_states):
    """Given list of raw state strings from DB, return sorted unique canonical names."""
    if not raw_states:
        return []
    seen = set()
    out = []
    for s in raw_states:
        if not s:
            continue
        c = normalize_state(s)
        if c not in seen:
            seen.add(c)
            out.append(c)
    return sorted(out)
