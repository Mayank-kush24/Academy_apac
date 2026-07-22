"""
Per-request cohort visibility, derived entirely from the CDI session JWT.

The legacy ``users.allowed_cohort_ids`` column is no longer consulted. A user's
cohort allow-list comes from the cohort-scoped portal page ids in
``moduleAccess[<this module>]`` (e.g. ``c1__dashboard`` -> cohort 1 access).
"""
from __future__ import annotations

from typing import List, Optional, TYPE_CHECKING

from flask import g

from server.cohort_config import ALLOWED_COHORT_IDS, is_cohort_enabled

if TYPE_CHECKING:
    from server.utils.auth import PortalUser


def _cdi_portal_admin() -> bool:
    u = getattr(g, "user", None)
    return isinstance(u, dict) and bool(u.get("isAdmin"))


def enabled_cohort_ids() -> List[int]:
    """Cohort ids that are enabled in config (e.g. 1 and 2; not disabled cohort 3)."""
    return [cid for cid in ALLOWED_COHORT_IDS if is_cohort_enabled(cid)]


def normalize_allowed_cohort_ids(raw) -> Optional[List[int]]:
    """
    Best-effort normalization for any external list of cohort ids.

    Returns ``None`` for "all enabled cohorts", or a non-empty list of allowed,
    enabled cohort ids. Kept for callers that still pass user-provided values.
    """
    if raw is None:
        return None
    if not isinstance(raw, list):
        raise ValueError("allowed_cohort_ids must be a list of integers or null")
    out: List[int] = []
    seen = set()
    for x in raw:
        try:
            cid = int(x)
        except (TypeError, ValueError):
            raise ValueError("allowed_cohort_ids must contain only integers")
        if cid not in ALLOWED_COHORT_IDS:
            raise ValueError(f"Invalid cohort id: {cid}")
        if not is_cohort_enabled(cid):
            continue
        if cid not in seen:
            seen.add(cid)
            out.append(cid)
    out.sort()
    if len(out) == 0:
        raise ValueError(
            "allowed_cohort_ids cannot be empty; use null for all enabled cohorts"
        )
    return out


def user_visible_cohort_ids(user: Optional["PortalUser"]) -> List[int]:
    """Cohort ids this user may access. Admins and unrestricted JWTs see all enabled."""
    if _cdi_portal_admin():
        return enabled_cohort_ids()
    if user is None:
        return []
    raw = getattr(user, "allowed_cohort_ids", None)
    if raw is None:
        # PortalUser._compute_allowed_cohorts returned None -> unrestricted.
        return enabled_cohort_ids()
    if not isinstance(raw, list) or len(raw) == 0:
        return []
    out: List[int] = []
    for x in raw:
        try:
            cid = int(x)
        except (TypeError, ValueError):
            continue
        if cid in ALLOWED_COHORT_IDS and is_cohort_enabled(cid) and cid not in out:
            out.append(cid)
    out.sort()
    return out


def user_may_access_cohort(user: Optional["PortalUser"], cohort_id: int) -> bool:
    if cohort_id not in ALLOWED_COHORT_IDS or not is_cohort_enabled(cohort_id):
        return False
    if _cdi_portal_admin():
        return True
    if user is None:
        # No JWT-derived user -> no cohort-scoped access granted.
        return False
    return cohort_id in user_visible_cohort_ids(user)
