"""
CDI-portal-only authentication.

The legacy DB-backed ``users`` table is no longer consulted. ``get_current_user()``
returns a lightweight :class:`PortalUser` shim derived entirely from the verified
CDI session JWT (``h2s_cdi_session`` cookie) so existing route code that reads
``user.email`` / ``user.role`` / ``user.allowed_pages`` / ``user.allowed_cohort_ids``
continues to work without DB writes.
"""
from __future__ import annotations

from functools import wraps
from typing import List, Optional

from flask import jsonify

from server.h2s_cdi_auth import get_module_pages, get_session_payload_from_request


class PortalUser:
    """Read-only user view backed by a verified CDI JWT payload (no DB row)."""

    __slots__ = (
        "_payload",
        "id",
        "name",
        "email",
        "role",
        "status",
        "allowed_pages",
        "allowed_cohort_ids",
        "password_hash",
        "created_at",
    )

    def __init__(self, payload: dict):
        self._payload = payload or {}
        email = (self._payload.get("email") or self._payload.get("sub") or "").strip()
        name = (self._payload.get("name") or "").strip() or email or "Portal user"
        self.id = None  # portal-only users have no local UUID
        self.email = email
        self.name = name
        self.role = "admin" if bool(self._payload.get("isAdmin")) else "viewer"
        self.status = "active"
        self.password_hash = None
        self.created_at = None
        self.allowed_pages = self._compute_allowed_pages()
        self.allowed_cohort_ids = self._compute_allowed_cohorts()

    @property
    def is_admin(self) -> bool:  # noqa: D401  (small utility property)
        return bool(self._payload.get("isAdmin"))

    @property
    def payload(self) -> dict:
        return self._payload

    def _module_pages(self) -> Optional[List[str]]:
        """Raw module pages list from JWT (may be None for unrestricted, [] for none)."""
        return get_module_pages(self._payload)

    def _compute_allowed_pages(self) -> Optional[List[str]]:
        """
        Logical page ids the user can access.

        - Admin or unrestricted JWT (None) -> ``None`` (caller treats null as "all").
        - Otherwise: union of logical page ids from the JWT, with cohort-scoped ids
          (e.g. ``c1__dashboard``) flattened to their logical name (``dashboard``).

        Used by the sidebar in base.html, which checks ``allowed_pages.indexOf(pageId)``
        against logical ids; cohort gating is enforced separately by ``allowed_cohort_ids``.
        """
        if self.is_admin:
            return None
        pages = self._module_pages()
        if pages is None:
            return None
        from server.cdi_integration import parse_cohort_portal_page_id

        out: set[str] = set()
        for p in pages:
            cid, logical = parse_cohort_portal_page_id(p)
            out.add(logical if cid is not None else p)
        return sorted(out)

    def _compute_allowed_cohorts(self) -> Optional[List[int]]:
        """
        Cohort ids derivable from JWT module pages.

        - Admin or unrestricted JWT (None) -> ``None`` (caller treats null as "all enabled").
        - JWT lists only logical pages (e.g. legacy ``dashboard``) -> ``None`` (no cohort
          constraint encoded in the JWT — fall back to all enabled cohorts).
        - JWT lists scoped pages -> sorted union of those cohort ids.
        """
        if self.is_admin:
            return None
        pages = self._module_pages()
        if pages is None:
            return None
        from server.cdi_integration import parse_cohort_portal_page_id

        cids: set[int] = set()
        has_logical_only = False
        for p in pages:
            cid, _ = parse_cohort_portal_page_id(p)
            if cid is None:
                if p != "home":
                    has_logical_only = True
            else:
                cids.add(cid)
        if cids:
            return sorted(cids)
        if has_logical_only:
            return None
        return []  # only "home" (or empty): no cohort access

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "role": self.role,
            "status": self.status,
            "allowed_pages": self.allowed_pages,
            "allowed_cohort_ids": self.allowed_cohort_ids,
            "created_at": self.created_at,
            "_source": "cdi_jwt",
        }


def get_current_user() -> Optional[PortalUser]:
    """Return a :class:`PortalUser` from the CDI session cookie, or ``None``."""
    payload = get_session_payload_from_request()
    if not payload:
        return None
    return PortalUser(payload)


def token_required(f):
    """Require a valid CDI portal session (no DB lookup)."""

    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if user is None:
            return jsonify({"error": "Authentication required"}), 401
        return f(*args, **kwargs)

    return decorated
