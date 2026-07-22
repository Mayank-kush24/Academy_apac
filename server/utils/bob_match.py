"""
Book of Business (BOB) match utility.
Sets user_pii / user_pii_injected.bob_match by comparing normalized organization_name
to cohort-prefixed bob_companies (e.g. cohort_2_bob_companies).

Recalculation uses PostgreSQL UPDATE + EXISTS so it does not depend on reflected ORM
models and matches trim+lower semantics consistently for BOB rows and user orgs.
"""
import re

from flask import g, has_app_context
from sqlalchemy import text

from server.models import db

_PREFIX_RE = re.compile(r"^$|^cohort_[0-9]+_$")


def _normalize(s):
    """Trim and lower for matching (same semantics as SQL btrim + lower)."""
    if s is None or not isinstance(s, str):
        return ""
    return s.strip().lower()


# Prefer non-empty normalized_name, else company_name — same as legacy Python import path.
# IS DISTINCT FROM avoids rewriting rows that already have the correct bob_match.
_BOB_MATCH_UPDATE_SQL = """
WITH computed AS (
    SELECT u.id AS uid,
        (
            btrim(COALESCE(u.organization_name, '')) <> ''
            AND EXISTS (
                SELECT 1 FROM {bob_tbl} AS b
                WHERE lower(btrim(COALESCE(u.organization_name, ''))) = lower(btrim(
                    CASE
                        WHEN b.normalized_name IS NOT NULL AND btrim(b.normalized_name) <> ''
                            THEN b.normalized_name
                        ELSE COALESCE(b.company_name, '')
                    END
                ))
            )
        ) AS new_bm
    FROM {pii_tbl} AS u
)
UPDATE {pii_tbl} AS u
SET bob_match = c.new_bm
FROM computed AS c
WHERE u.id = c.uid AND u.bob_match IS DISTINCT FROM c.new_bm
"""


def recalculate_bob_match_with_prefix(prefix: str) -> int:
    """
    Recompute bob_match for user_pii and user_pii_injected using raw SQL.
    prefix: '' (cohort 1) or 'cohort_2_', etc.
    Returns total rowcount from both UPDATEs (may be -1 on some drivers; summed as 0).
    """
    prefix = prefix or ""
    if not _PREFIX_RE.match(prefix):
        raise ValueError(f"Invalid table prefix: {prefix!r}")

    pii = f"{prefix}user_pii"
    inj = f"{prefix}user_pii_injected"
    bob = f"{prefix}bob_companies"

    total = 0
    for pii_tbl in (pii, inj):
        stmt = text(_BOB_MATCH_UPDATE_SQL.format(pii_tbl=pii_tbl, bob_tbl=bob))
        result = db.session.execute(stmt)
        rc = result.rowcount
        if rc is not None and rc >= 0:
            total += rc
    db.session.commit()
    return total


def recalculate_bob_match():
    """
    Recompute bob_match for the current request cohort (g.table_prefix).
    Requires Flask app context and cohort-scoped request (or worker that set g.table_prefix).
    """
    if not has_app_context():
        raise RuntimeError("recalculate_bob_match requires Flask app context")
    prefix = getattr(g, "table_prefix", None) or ""
    return recalculate_bob_match_with_prefix(prefix)


def get_bob_company_names_with_prefix(prefix: str = "") -> list[str]:
    """
    Load BOB company_name values from the cohort bob_companies table.
    prefix: '' (cohort 1) or 'cohort_2_', etc.
    """
    prefix = prefix or ""
    if not _PREFIX_RE.match(prefix):
        raise ValueError(f"Invalid table prefix: {prefix!r}")

    bob_tbl = f"{prefix}bob_companies"
    stmt = text(
        f"SELECT company_name FROM {bob_tbl} "
        "WHERE company_name IS NOT NULL AND btrim(company_name) <> '' "
        "ORDER BY id"
    )
    rows = db.session.execute(stmt).fetchall()
    return [str(row[0]).strip() for row in rows if row[0] and str(row[0]).strip()]


def cohort_id_to_prefix(cohort_id: int | None) -> str:
    """Map cohort id to physical table prefix ('' for cohort 1)."""
    if cohort_id is None or cohort_id <= 1:
        return ""
    return f"cohort_{int(cohort_id)}_"


def get_bob_company_names_for_cohort(cohort_id: int | None = 2) -> list[str]:
    """
    Load BOB company names for a cohort inside Flask app context.
    Default cohort_id=2 matches the active Cohort 2 deployment.
    """
    if not has_app_context():
        raise RuntimeError("get_bob_company_names_for_cohort requires Flask app context")
    return get_bob_company_names_with_prefix(cohort_id_to_prefix(cohort_id))


def get_bob_normalized_set():
    """
    Load normalized BOB keys (for diagnostics/tests). Uses ORM + participant_model;
    prefers cohort-prefixed bob_companies when g.table_prefix is set.
    """
    from server.models import BobCompany
    from server.utils.cohort_participant_models import participant_model

    Bob = participant_model(BobCompany)
    names = set()
    for row in Bob.query.with_entities(Bob.normalized_name, Bob.company_name).all():
        nn, cn = row[0], row[1]
        if nn is not None and str(nn).strip() != "":
            base = nn
        else:
            base = cn
        if base is None:
            continue
        n = _normalize(str(base))
        if n:
            names.add(n)
    return names
