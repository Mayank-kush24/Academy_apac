"""
Request-scoped cohort id + table_prefix for multi-cohort routing.

Every request that touches cohort-scoped data gets:
  g.cohort_id    – int | None
  g.table_prefix – str  (e.g. "" for cohort 1, "cohort_2_" for cohort 2)

Routes use g.table_prefix when building raw-SQL table names:
    tbl = f"{g.table_prefix}user_pii"
    db.session.execute(text(f"SELECT * FROM {tbl} WHERE email = :e"), {"e": email})

All tables live in the PUBLIC schema; isolation is via the table-name prefix,
not via SET LOCAL search_path.
"""
import re
from typing import Optional

from flask import abort, g, jsonify, make_response, request

from server.cohort_config import (
    ALLOWED_COHORT_IDS,
    get_table_prefix,
    is_cohort_api_path_disabled,
    is_cohort_enabled,
)

# API prefixes that require ?cohort_id= (or X-Cohort-Id header) on every request.
COHORT_API_PREFIXES = (
    "/api/import",
    "/api/dashboard",
    "/api/profiles",
    "/api/skilllab",
    "/api/book-of-business",
    "/api/users-registrations",
    "/api/skilllab-submission",
    "/api/codelab-submission",
    "/api/project-submission",
    "/api/mcq-verification",
    "/api/import-user-pii-injected",
    "/api/track-progress",
)

_COHORT_HTML_PATH = re.compile(r"^/c/(\d+)(?:/|$)")

# Longest first so /api/import-user-pii-injected wins over /api/import
_COHORT_API_PREFIXES_SORTED = tuple(sorted(COHORT_API_PREFIXES, key=len, reverse=True))


def _path_needs_cohort_api(path: str) -> bool:
    return any(path == p or path.startswith(p + "/") for p in _COHORT_API_PREFIXES_SORTED)


def _parse_cohort_id_from_path() -> Optional[int]:
    m = _COHORT_HTML_PATH.match(request.path)
    if not m:
        return None
    return int(m.group(1))


def _parse_cohort_id_from_api() -> Optional[int]:
    cid = request.args.get("cohort_id", type=int)
    if cid is not None:
        return cid
    raw = (request.headers.get("X-Cohort-Id") or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _set_cohort(cohort_id: int) -> None:
    """Store cohort_id and its table_prefix on flask.g."""
    g.cohort_id = cohort_id
    g.table_prefix = get_table_prefix(cohort_id)


def _enforce_user_cohort_for_api() -> None:
    """403 when JWT user may not access g.cohort_id (cohort-scoped JSON APIs only)."""
    path = request.path or ""
    if not _path_needs_cohort_api(path):
        return
    cid = getattr(g, "cohort_id", None)
    if cid is None:
        return
    from server.utils.auth import get_current_user
    from server.utils.cohort_access import user_may_access_cohort

    user = get_current_user()
    if user and not user_may_access_cohort(user, cid):
        abort(
            make_response(
                jsonify(
                    {
                        "error": "You do not have access to this cohort.",
                        "cohort_id": cid,
                    }
                ),
                403,
            )
        )


def init_cohort_for_request() -> None:
    """
    Set g.cohort_id and g.table_prefix for the current request.

    - HTML pages under /c/<id>/... set cohort from the URL path.
    - Cohort-scoped API endpoints require cohort_id query param or X-Cohort-Id header.
    - All other paths (auth, admin, users, /, /login) get cohort_id=None, prefix="".
    """
    g.cohort_id = None
    g.table_prefix = ""

    path = request.path or ""

    if path.startswith("/static"):
        return

    if request.method == "OPTIONS":
        return

    # Cohort from browser HTML routes  /c/<id>/...
    html_cohort = _parse_cohort_id_from_path()
    if html_cohort is not None:
        if html_cohort not in ALLOWED_COHORT_IDS:
            abort(404)
        if not is_cohort_enabled(html_cohort):
            abort(404)
        _set_cohort(html_cohort)
        _enforce_user_cohort_for_api()
        return

    # JSON APIs that are cohort-scoped
    if _path_needs_cohort_api(path):
        cid = _parse_cohort_id_from_api()
        if cid is None:
            abort(
                make_response(
                    jsonify(
                        {
                            "error": "cohort_id is required",
                            "hint": "Add cohort_id query parameter or X-Cohort-Id header.",
                        }
                    ),
                    400,
                )
            )
        if cid not in ALLOWED_COHORT_IDS or not is_cohort_enabled(cid):
            abort(
                make_response(
                    jsonify({"error": "Invalid or disabled cohort_id"}),
                    400,
                )
            )
        _set_cohort(cid)
        if is_cohort_api_path_disabled(cid, path):
            abort(
                make_response(
                    jsonify({"error": "This module is not enabled for this cohort."}),
                    404,
                )
            )
        _enforce_user_cohort_for_api()
        return

    # Global paths (auth, users, admin, /, /login) — no cohort, no prefix.


def register_cohort_context(app):
    @app.before_request
    def _cohort_context_before_request():
        init_cohort_for_request()
