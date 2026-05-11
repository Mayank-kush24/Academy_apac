"""
Optional Hack2skill CDI (portal) integration: env-gated ProxyFix, path rules, portal registration.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Tuple

import re

from server.cohort_config import (
    ALLOWED_COHORT_IDS,
    get_cohort_entry,
    is_cohort_enabled,
    is_cohort_html_page_disabled,
)
from server.utils.permissions import PAGES

# Portal pageId for cohort-scoped L2 permissions: c{cohort_id}__{logical_page_id}
# (double underscore so logical ids with underscores stay unambiguous.)
_COHORT_PORTAL_PAGE_RE = re.compile(r"^c(\d+)__(.+)$")


def cohort_portal_page_id(cohort_id: int, logical_page_id: str) -> str:
    return f"c{cohort_id}__{logical_page_id}"


def parse_cohort_portal_page_id(page_id: str) -> tuple[int | None, str]:
    m = _COHORT_PORTAL_PAGE_RE.match(page_id or "")
    if m:
        return int(m.group(1)), m.group(2)
    return None, page_id or ""


def portal_page_id_to_app_path(page_id: str) -> str:
    """Map a registered portal pageId (scoped or legacy logical) to PATH_INFO for redirects."""
    cid, logical = parse_cohort_portal_page_id(page_id)
    lid = logical if cid is not None else (page_id or "")
    if lid == "home":
        return "/home"
    for p in PAGES:
        if p["id"] != lid:
            continue
        slug = p.get("slug")
        if not slug:
            return "/"
        cohort = cid if cid is not None else 1
        return f"/c/{cohort}/{slug}"
    return "/"


def effective_cohort_id_for_l2_check() -> int | None:
    """
    Cohort for matching scoped portal pageIds.

    Runs from CDI before_request (often before cohort_context), so path/query/header
    are resolved here rather than relying only on flask.g.cohort_id.
    """
    from flask import g, request

    path = request.path or ""
    m = re.match(r"^/c/(\d+)(?:/|$)", path)
    if m:
        return int(m.group(1))
    cid = request.args.get("cohort_id", type=int)
    if cid is not None:
        return cid
    raw = (request.headers.get("X-Cohort-Id") or "").strip()
    if raw.isdigit():
        return int(raw)
    gc = getattr(g, "cohort_id", None)
    return int(gc) if gc is not None else None


def portal_allowlist_allows_logical_page(mod_pages: list[str], logical_page_id: str) -> bool:
    """True if JWT module page list grants this logical page for the current request cohort (or legacy)."""
    if logical_page_id in mod_pages:
        return True
    eff = effective_cohort_id_for_l2_check()
    if eff is not None and cohort_portal_page_id(eff, logical_page_id) in mod_pages:
        return True
    return False


def portal_allowlist_allows_resolved_page(mod_pages: list[str], resolved_page: str) -> bool:
    """
    True if JWT allows this path-derived page id (cohort-scoped id from HTML routes,
    or logical id from API prefix rules).
    """
    if resolved_page in mod_pages:
        return True
    cid, logical = parse_cohort_portal_page_id(resolved_page)
    if cid is not None:
        if logical in mod_pages:
            return True
        return False
    eff = effective_cohort_id_for_l2_check()
    if eff is not None and cohort_portal_page_id(eff, resolved_page) in mod_pages:
        return True
    return False


def is_cdi_enabled() -> bool:
    """True when portal CDI secrets and module id are configured (this app is CDI-only)."""
    jwt_s = (os.environ.get("H2S_CDI_JWT_SECRET") or os.environ.get("JARVIS_JWT_SECRET") or "").strip()
    mid = (os.environ.get("H2S_CDI_MODULE_ID") or os.environ.get("JARVIS_MODULE_ID") or "").strip()
    return bool(jwt_s and mid)


def assert_cdi_auth_configured() -> None:
    """Fail fast at startup: this deployment authenticates only via the CDI portal cookie."""
    if not is_cdi_enabled():
        raise RuntimeError(
            "CDI authentication is required. Set H2S_CDI_JWT_SECRET and H2S_CDI_MODULE_ID "
            "(and H2S_CDI_URL, H2S_CDI_REGISTRATION_SECRET, APPLICATION_ROOT if mounted under a path). "
            "Legacy app JWT / password login is disabled."
        )


def _slug_to_page_id() -> Dict[str, str]:
    m: Dict[str, str] = {}
    for p in PAGES:
        slug = p.get("slug")
        if slug:
            m[slug] = p["id"]
    return m


def _legacy_path_cohort_id() -> int:
    """Cohort id used for old non-/c/... URLs (treat as Cohort 1 when enabled)."""
    if is_cohort_enabled(1):
        return 1
    for cid in ALLOWED_COHORT_IDS:
        if is_cohort_enabled(cid):
            return cid
    return 1


def build_module_pages_for_portal() -> List[Dict[str, Any]]:
    """
    Page list for register_with_portal: one row per (enabled cohort × page), grouped by cohort.

    Each dict includes optional ``group`` (cohort label) for CDI portal UI grouping.
    ``pageId`` is cohort-scoped (e.g. c2__dashboard) except ``home``, which stays global.
    """
    out: List[Dict[str, Any]] = []
    home_row = next((p for p in PAGES if p["id"] == "home"), None)
    out.append(
        {
            "pageId": "home",
            "label": (home_row or {}).get("label", "Home"),
            # Register at /home (CDI portal convention from module_template) — Flask
            # serves the same template at both / and /home.
            "path": "/home",
            "group": "All cohorts",
        }
    )
    for cid in ALLOWED_COHORT_IDS:
        if not is_cohort_enabled(cid):
            continue
        entry = get_cohort_entry(cid) or {}
        group_label = str(entry.get("label") or f"Cohort {cid}")
        # Short cohort marker prefixed onto page labels (e.g. "C1 Dashboard", "C2 Dashboard").
        # The portal UI currently renders a flat list, so the marker disambiguates same-named
        # pages across cohorts. ``group`` is also kept for future grouped-UI support.
        cohort_marker = f"C{cid}"
        for p in PAGES:
            logical = p["id"]
            slug = p.get("slug")
            if not slug:
                continue
            if is_cohort_html_page_disabled(cid, slug):
                continue
            path = f"/c/{cid}/{slug}"
            out.append(
                {
                    "pageId": cohort_portal_page_id(cid, logical),
                    "label": f"{cohort_marker} {p['label']}",
                    "path": path,
                    "group": group_label,
                }
            )
    return out


def build_cdi_path_page_rules() -> List[Tuple[str, str]]:
    """
    Map URL prefixes to portal pageIds (must match MODULE_PAGES / portal permissions).
    Longest-prefix wins inside h2s_cdi_auth.
    """
    slug_to_pid = _slug_to_page_id()
    rules: List[Tuple[str, str]] = []

    for cid in ALLOWED_COHORT_IDS:
        if not is_cohort_enabled(cid):
            continue
        for slug, logical in slug_to_pid.items():
            if is_cohort_html_page_disabled(cid, slug):
                continue
            rules.append((f"/c/{cid}/{slug}", cohort_portal_page_id(cid, logical)))
        if not is_cohort_html_page_disabled(cid, "import"):
            rules.append((f"/c/{cid}/import-user-pii-injected", cohort_portal_page_id(cid, "import")))

    leg_c = _legacy_path_cohort_id()
    legacy = [
        ("/dashboard", cohort_portal_page_id(leg_c, "dashboard")),
        ("/import", cohort_portal_page_id(leg_c, "import")),
        ("/import-user-pii-injected", cohort_portal_page_id(leg_c, "import")),
        ("/profiles", cohort_portal_page_id(leg_c, "profiles")),
        ("/skill-lab-credits", cohort_portal_page_id(leg_c, "skill_lab_credits")),
        ("/book-of-business", cohort_portal_page_id(leg_c, "book_of_business")),
        ("/users-registrations", cohort_portal_page_id(leg_c, "users_registrations")),
        ("/skilllab-submission", cohort_portal_page_id(leg_c, "skilllab_submission")),
        ("/codelab-submission", cohort_portal_page_id(leg_c, "codelab_submission")),
        ("/project-submission", cohort_portal_page_id(leg_c, "project_submission")),
        ("/optional-mcq-verification", cohort_portal_page_id(leg_c, "optional_mcq_verification")),
        ("/mcq-verification", cohort_portal_page_id(leg_c, "mcq_verification")),
        ("/track-progress-query", cohort_portal_page_id(leg_c, "track_progress_query")),
    ]
    rules.extend(legacy)

    rules.extend(
        [
            ("/api/import-user-pii-injected", "import"),
            ("/api/import", "import"),
            ("/api/dashboard", "dashboard"),
            ("/api/profiles", "profiles"),
            ("/api/skilllab", "skill_lab_credits"),
            ("/api/book-of-business", "book_of_business"),
            ("/api/users-registrations", "users_registrations"),
            ("/api/skilllab-submission", "skilllab_submission"),
            ("/api/codelab-submission", "codelab_submission"),
            ("/api/project-submission", "project_submission"),
            ("/api/mcq-verification/main", "mcq_verification"),
            ("/api/mcq-verification", "optional_mcq_verification"),
            ("/api/track-progress", "track_progress_query"),
        ]
    )

    return rules


def cdi_public_path_prefixes() -> Tuple[str, ...]:
    return (
        "/static",
        "/favicon.ico",
        "/health",
        "/login",
        "/logout",
        "/api/auth/login",
        "/",
        "/home",
    )
