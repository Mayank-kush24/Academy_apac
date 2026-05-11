"""
Per-user cohort visibility (RBAC). Complements allowed_pages on User.

allowed_cohort_ids on users:
  None  → may access every cohort that is enabled in cohort_config.
  [1,2] → may access only those cohort ids (must be enabled; others stripped on save).
"""
from __future__ import annotations

from typing import List, Optional, TYPE_CHECKING

from flask import g

from server.cohort_config import ALLOWED_COHORT_IDS, is_cohort_enabled


def _cdi_portal_admin() -> bool:
    u = getattr(g, "user", None)
    return isinstance(u, dict) and bool(u.get("isAdmin"))

if TYPE_CHECKING:
    from server.models import User


def enabled_cohort_ids() -> List[int]:
    """Cohort ids that are enabled in config (e.g. 1 and 2; not disabled cohort 3)."""
    return [cid for cid in ALLOWED_COHORT_IDS if is_cohort_enabled(cid)]


def normalize_allowed_cohort_ids(raw) -> Optional[List[int]]:
    """
    Validate and normalize JSON value for User.allowed_cohort_ids.
    Returns None for 'all enabled cohorts', or a non-empty list of allowed ids.
    Raises ValueError on invalid input.
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


def user_visible_cohort_ids(user: Optional["User"]) -> List[int]:
    """Cohort ids this user may access (for UI and checks). Admins: all enabled."""
    if _cdi_portal_admin():
        return enabled_cohort_ids()
    if not user or user.status != "active":
        return []
    if getattr(user, "role", None) == "admin":
        return enabled_cohort_ids()
    raw = getattr(user, "allowed_cohort_ids", None)
    if raw is None:
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


def user_may_access_cohort(user: Optional["User"], cohort_id: int) -> bool:
    if cohort_id not in ALLOWED_COHORT_IDS or not is_cohort_enabled(cohort_id):
        return False
    if _cdi_portal_admin():
        return True
    if not user or user.status != "active":
        return False
    if getattr(user, "role", None) == "admin":
        return True
    return cohort_id in user_visible_cohort_ids(user)
