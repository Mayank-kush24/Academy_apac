"""
Cohort definitions: URL ids, labels, table prefix per cohort.

All Cohort 2+ tables live in the PUBLIC schema but are named with a prefix,
e.g. cohort_2_user_pii, cohort_2_user_pii_injected, cohort_2_bob_companies …
Cohort 1 uses the original unqualified names (user_pii, user_pii_injected, …).

table_prefix:
  ""       → Cohort 1: original tables, no prefix.
  "cohort_2_" → Cohort 2: all tables prefixed with cohort_2_.
  "cohort_3_" → Cohort 3: all tables prefixed with cohort_3_.

Routes access the prefix via  flask.g.table_prefix  (set per-request).
"""
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

# Cohort numeric ids used in /c/<id>/... and ?cohort_id=
ALLOWED_COHORT_IDS: Tuple[int, ...] = (1, 2, 3)

COHORTS: Dict[int, Dict[str, Any]] = {
    1: {
        "label": "Cohort 1",
        "table_prefix": "",          # original tables – no prefix, no schema switch
        "schema": None,              # public schema (unchanged)
        "enabled": True,
        "description": "Original program data.",
    },
    2: {
        "label": "Cohort 2",
        "table_prefix": "cohort_2_", # e.g. cohort_2_user_pii
        "schema": None,              # still public schema
        "enabled": True,
        "description": "Second program intake.",
        # Sidebar + HTML/API: these modules are hidden and return 404 for cohort 2.
        "disabled_pages": (
            "project-submission",
            "track-progress-query",
            # Skill Lab credits, Skill Lab Submissions verification, and dashboard Skill Lab row like Cohort 1.
            # Dashboard-only: Code Lab KPI card in kpi-small-row (page / sidebar stay enabled).
            "codelab-submission-dashboard",
        ),
        "disabled_api_prefixes": (
            "/api/project-submission",
            "/api/track-progress",
        ),
    },
    3: {
        "label": "Cohort 3",
        "table_prefix": "cohort_3_", # e.g. cohort_3_user_pii
        "schema": None,
        "enabled": True,
        "description": "Third program intake (UTS API sync).",
        # Registration Trend x-axis for period=all. C3 onboarding started mid-July;
        # Jan 15 (C1/C2 default) leaves months of zeros and compresses the real series.
        "registration_trend_start": date(2026, 7, 15),
        # Same module set as Cohort 2.
        "disabled_pages": (
            "project-submission",
            "track-progress-query",
            "codelab-submission-dashboard",
        ),
        "disabled_api_prefixes": (
            "/api/project-submission",
            "/api/track-progress",
        ),
    },
}


def get_cohort_entry(cohort_id: int) -> Optional[Dict[str, Any]]:
    return COHORTS.get(cohort_id)


def is_cohort_enabled(cohort_id: int) -> bool:
    entry = get_cohort_entry(cohort_id)
    return bool(entry and entry.get("enabled"))


def cohort_postgres_schemas() -> List[str]:
    """Physical cohort schemas (cohort 2+). Used for migrations and ensuring views."""
    out = []
    for cid in ALLOWED_COHORT_IDS:
        entry = get_cohort_entry(cid)
        if not entry:
            continue
        s = entry.get("schema")
        if s:
            out.append(s)
    return out


def cohort_list_for_template() -> List[Dict[str, Any]]:
    """For home hub cards."""
    rows = []
    for cid in ALLOWED_COHORT_IDS:
        entry = get_cohort_entry(cid) or {}
        rows.append(
            {
                "id": cid,
                "label": entry.get("label", f"Cohort {cid}"),
                "description": entry.get("description", ""),
                "enabled": bool(entry.get("enabled")),
            }
        )
    return rows


def cohort_disabled_pages(cohort_id: Optional[int]) -> frozenset:
    """URL slugs under /c/<id>/... that are disabled for this cohort."""
    if cohort_id is None:
        return frozenset()
    entry = get_cohort_entry(cohort_id)
    if not entry:
        return frozenset()
    return frozenset(entry.get("disabled_pages") or ())


def cohort_disabled_api_prefixes(cohort_id: int) -> frozenset:
    """API path prefixes (e.g. /api/skilllab) disabled for this cohort."""
    entry = get_cohort_entry(cohort_id)
    if not entry:
        return frozenset()
    return frozenset(entry.get("disabled_api_prefixes") or ())


def is_cohort_html_page_disabled(cohort_id: int, page_slug: str) -> bool:
    return page_slug in cohort_disabled_pages(cohort_id)


def is_cohort_api_path_disabled(cohort_id: int, path: str) -> bool:
    prefixes = cohort_disabled_api_prefixes(cohort_id)
    if not prefixes:
        return False
    for p in sorted(prefixes, key=len, reverse=True):
        if path == p or path.startswith(p + "/"):
            return True
    return False


def get_registration_trend_start(table_prefix: str = "", today: Optional[date] = None) -> date:
    """First day on the Registration Trend x-axis when the dashboard period is 'all'.

    Cohort 1/2 use 15 Jan of the current program year. Cohort 3 uses its configured
    open date so the chart is not padded with empty months before onboarding began.
    """
    today = today or date.today()
    prefix = table_prefix or ""
    for entry in COHORTS.values():
        if (entry.get("table_prefix") or "") == prefix:
            configured = entry.get("registration_trend_start")
            if configured:
                if isinstance(configured, date):
                    return configured
                return date.fromisoformat(str(configured))
            break
    start = date(today.year, 1, 15)
    if start > today:
        start = date(today.year - 1, 1, 15)
    return start


def get_table_prefix(cohort_id: int) -> str:
    """
    Return the table-name prefix for this cohort.
    Cohort 1 → ""   (use tables as-is: user_pii, …)
    Cohort 2 → "cohort_2_"  (use cohort_2_user_pii, …)
    """
    entry = get_cohort_entry(cohort_id)
    if not entry:
        return ""
    return entry.get("table_prefix", "")


def search_path_clause(cohort_id: int) -> str:
    """
    Kept for backward compatibility.
    All cohorts now use the public schema; table prefix is the isolation mechanism.
    """
    return "public"
