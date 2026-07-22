"""
Create or replace user_pii_combined views.

Cohort 1 (public schema, no prefix): view  user_pii_combined
Cohort 2 (public schema, prefix cohort_2_): view  cohort_2_user_pii_combined
"""
from sqlalchemy import text

from server.cohort_config import ALLOWED_COHORT_IDS, get_cohort_entry, get_table_prefix


def _view_sql(prefix: str, src_has_display: bool = False, injected_has_display: bool = False) -> str:
    """Build CREATE VIEW SQL for a given table-name prefix (empty string = cohort 1).

    ``display_registered_at`` is a graph-only override of ``registered_at`` used to
    reshape the Registration Trend chart without altering real registration dates.
    It is always exposed by the view; when a base table lacks the column we emit
    ``NULL`` so downstream ``COALESCE(display_registered_at, registered_at)`` is a no-op.
    """
    view  = f"{prefix}user_pii_combined"
    src   = f"{prefix}user_pii"
    injected = f"{prefix}user_pii_injected"
    src_display = "display_registered_at" if src_has_display else "NULL::timestamp AS display_registered_at"
    injected_display = "display_registered_at" if injected_has_display else "NULL::timestamp AS display_registered_at"
    return f"""
        DROP VIEW IF EXISTS {view} CASCADE;
        CREATE VIEW {view} AS
        SELECT id, registered_at, {src_display}, organization_name, class_stream, domain, designation, name, email,
               mobile_number, country, state, city, date_of_birth, gender, occupation,
               github_url, linkedin_url, utm_medium, bob_match, industry, persona,
               sub_category, broad_category, created_at, updated_at,
               'user_pii'::text AS source
        FROM {src}
        UNION ALL
        SELECT id, registered_at, {injected_display}, organization_name, class_stream, domain, designation, name, email,
               mobile_number, country, state, city, date_of_birth, gender, occupation,
               github_url, linkedin_url, utm_medium, bob_match, industry, persona,
               sub_category, broad_category, created_at, updated_at,
               'user_pii_injected'::text AS source
        FROM {injected} i
        WHERE NOT EXISTS (SELECT 1 FROM {src} u WHERE u.email = i.email)
    """


def ensure_user_pii_combined_views(engine):
    """Ensure user_pii_combined view exists for every enabled cohort whose tables are present."""
    from sqlalchemy import inspect as sa_inspect

    insp = sa_inspect(engine)
    existing_tables = set(insp.get_table_names(schema="public"))

    for cid in ALLOWED_COHORT_IDS:
        entry = get_cohort_entry(cid)
        if not entry:
            continue
        prefix = get_table_prefix(cid)
        pii_table = f"{prefix}user_pii"
        pii_injected_table = f"{prefix}user_pii_injected"

        if pii_injected_table not in existing_tables and pii_table not in existing_tables:
            continue  # tables not created yet – skip silently

        def _has_display(table_name: str) -> bool:
            if table_name not in existing_tables:
                return False
            return any(c["name"] == "display_registered_at" for c in insp.get_columns(table_name, schema="public"))

        try:
            with engine.connect() as conn:
                conn.execute(text(_view_sql(
                    prefix,
                    src_has_display=_has_display(pii_table),
                    injected_has_display=_has_display(pii_injected_table),
                )))
                conn.commit()
            label = f"cohort {cid}" if prefix else "cohort 1 (public)"
            print(f"[OK] {prefix}user_pii_combined view ({label})")
        except Exception as e:
            label = prefix or "public"
            print(f"[WARNING] Could not create {prefix}user_pii_combined view: {e}")
