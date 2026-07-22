"""
Page-level access control for the CDI portal.

This module is JWT-only. The legacy DB-backed ``users`` table is no longer
consulted; access is decided entirely by the verified ``h2s_cdi_session`` cookie:

- ``isAdmin`` in the JWT  -> all pages, all cohorts.
- ``moduleAccess[<this module id>]`` -> explicit allow-list of portal page ids
  (logical ids like ``dashboard`` and/or cohort-scoped ids like ``c2__dashboard``).
- Missing JWT -> 401. Authenticated but not allowed -> 403.
"""
from functools import wraps
from typing import Optional

from flask import g, jsonify

from server.h2s_cdi_auth import get_module_pages
from server.utils.auth import PortalUser, get_current_user


def _portal_jwt_payload() -> Optional[dict]:
    u = getattr(g, "user", None)
    return u if isinstance(u, dict) else None


def _portal_jwt_is_admin() -> bool:
    p = _portal_jwt_payload()
    return bool(p and p.get("isAdmin"))


def _portal_jwt_active() -> bool:
    return _portal_jwt_payload() is not None


# Page ids used in nav and the portal page registration. Slug is the path segment
# under /c/<cohort_id>/...; ``home`` is the global module landing.
PAGES = [
    {'id': 'home', 'slug': None, 'path': '/', 'label': 'Home'},
    {'id': 'dashboard', 'slug': 'dashboard', 'path': '/c/<cohort>/dashboard', 'label': 'Dashboard'},
    {'id': 'profiles', 'slug': 'profiles', 'path': '/c/<cohort>/profiles', 'label': 'Profiles'},
    {'id': 'skill_lab_credits', 'slug': 'skill-lab-credits', 'path': '/c/<cohort>/skill-lab-credits', 'label': 'Skill Lab credits'},
    {'id': 'book_of_business', 'slug': 'book-of-business', 'path': '/c/<cohort>/book-of-business', 'label': 'Book of Business Registrations'},
    {'id': 'users_registrations', 'slug': 'users-registrations', 'path': '/c/<cohort>/users-registrations', 'label': 'Users'},
    {'id': 'skilllab_submission', 'slug': 'skilllab-submission', 'path': '/c/<cohort>/skilllab-submission', 'label': 'Skill Lab Submissions'},
    {'id': 'codelab_submission', 'slug': 'codelab-submission', 'path': '/c/<cohort>/codelab-submission', 'label': 'Code Lab Submissions'},
    {'id': 'project_submission', 'slug': 'project-submission', 'path': '/c/<cohort>/project-submission', 'label': 'Project Submissions'},
    {'id': 'optional_mcq_verification', 'slug': 'optional-mcq-verification', 'path': '/c/<cohort>/optional-mcq-verification', 'label': 'Optional MCQ Verification'},
    {'id': 'mcq_verification', 'slug': 'mcq-verification', 'path': '/c/<cohort>/mcq-verification', 'label': 'MCQ Verification'},
    {'id': 'track_progress_query', 'slug': 'track-progress-query', 'path': '/c/<cohort>/track-progress-query', 'label': 'Track Progress Query'},
    {'id': 'import', 'slug': 'import', 'path': '/c/<cohort>/import', 'label': 'Import Data'},
]


def can_access_page(user, page_id: str) -> bool:
    """
    True if the current request is allowed to access ``page_id``.

    ``user`` may be ``None`` (portal-only request without DB row) or a
    :class:`PortalUser`. The decision is made entirely from the JWT.
    """
    if _portal_jwt_is_admin():
        return True
    if not _portal_jwt_active():
        return False
    mod_pages = get_module_pages()
    if mod_pages is None:
        # Module access not constrained for this user -> all pages allowed.
        return True
    if not mod_pages:
        return False
    if page_id in mod_pages:
        return True
    from server.cdi_integration import portal_allowlist_allows_logical_page

    return portal_allowlist_allows_logical_page(mod_pages, page_id)


def require_role(*allowed_roles):
    """
    Decorator preserved for compatibility with existing route code.

    Portal users are admin or viewer (derived from ``isAdmin``). Non-portal callers
    are rejected with 401.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if _portal_jwt_is_admin():
                return f(*args, **kwargs)
            if not _portal_jwt_active():
                return jsonify({'error': 'Authentication required'}), 401
            user: Optional[PortalUser] = get_current_user()
            role = (user.role if user else "viewer")
            if role not in allowed_roles:
                return jsonify({'error': 'Insufficient permissions'}), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def require_page_access(page_id: str):
    """
    Require access to ``page_id`` based solely on the verified CDI JWT.

    - 401 if no JWT.
    - 403 if JWT does not grant this page (logical or cohort-scoped form).
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if _portal_jwt_is_admin():
                return f(*args, **kwargs)
            if not _portal_jwt_active():
                return jsonify({'error': 'Authentication required'}), 401
            if not can_access_page(None, page_id):
                return jsonify({'error': 'Access not allowed to this page'}), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator
