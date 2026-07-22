"""
Database migration: add performance indexes for cohort-prefixed tables (Cohort 2 & 3).

The original add_indexes.py only indexed the unprefixed Cohort 1 tables. The Cohort 2/3
dashboards run the same GROUP BY / period-filter / overlap queries against cohort_2_* and
cohort_3_* tables, which currently sequential-scan. This script mirrors the Cohort 1 indexes
onto the prefixed tables, and adds functional lower(trim(email)) indexes needed by the
cross-cohort overlap query used for the "net new registrations" KPI.

Run from project root:
  python server/migrations/add_cohort_indexes.py                 # cohort_2_ and cohort_3_
  python server/migrations/add_cohort_indexes.py --prefix cohort_3_
  python server/migrations/add_cohort_indexes.py --overlap-only   # only the email indexes

Does NOT start the full Flask app (avoids create_all / view rebuilds / lock contention).
Uses DATABASE_URL from .env only. CREATE INDEX can take minutes on large tables; progress is
printed before each statement. If it appears stuck, stop the Flask server first (lock contention).
"""
import sys
import os

script_path = os.path.abspath(__file__)
migrations_dir = os.path.dirname(script_path)
server_dir = os.path.dirname(migrations_dir)
project_root = os.path.dirname(server_dir)

if project_root not in sys.path:
    sys.path.insert(0, project_root)
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

from dotenv import load_dotenv
from sqlalchemy import create_engine, text


# Prefixed cohorts that have parallel tables (see create_cohort2_tables.py / create_cohort3_tables.py)
DEFAULT_PREFIXES = ["cohort_2_", "cohort_3_"]


def _pii_table_indexes(prefix: str, table: str) -> list:
    """Indexes for a {prefix}{table} PII table (user_pii or user_pii_injected)."""
    p = prefix
    return [
        (f"CREATE INDEX IF NOT EXISTS idx_{p}{table}_registered_at ON {p}{table}(registered_at)",
         f"{p}{table} registered_at"),
        (f"CREATE INDEX IF NOT EXISTS idx_{p}{table}_country ON {p}{table}(country)",
         f"{p}{table} country"),
        (f"CREATE INDEX IF NOT EXISTS idx_{p}{table}_state ON {p}{table}(state)",
         f"{p}{table} state"),
        (f"CREATE INDEX IF NOT EXISTS idx_{p}{table}_city ON {p}{table}(city)",
         f"{p}{table} city"),
        (f"CREATE INDEX IF NOT EXISTS idx_{p}{table}_bob_match ON {p}{table}(bob_match)",
         f"{p}{table} bob_match"),
        (f"CREATE INDEX IF NOT EXISTS idx_{p}{table}_occupation ON {p}{table}(occupation)",
         f"{p}{table} occupation"),
        (f"CREATE INDEX IF NOT EXISTS idx_{p}{table}_domain ON {p}{table}(domain)",
         f"{p}{table} domain"),
        (f"CREATE INDEX IF NOT EXISTS idx_{p}{table}_organization ON {p}{table}(organization_name)",
         f"{p}{table} organization_name"),
        (f"CREATE INDEX IF NOT EXISTS idx_{p}{table}_gender ON {p}{table}(gender)",
         f"{p}{table} gender"),
        # Country + registered_at composite covers the frequent "APAC by period" style filters.
        (f"CREATE INDEX IF NOT EXISTS idx_{p}{table}_country_registered_at ON {p}{table}(country, registered_at)",
         f"{p}{table} country+registered_at"),
        # Functional index for the cross-cohort overlap query (LOWER(TRIM(email))).
        (f"CREATE INDEX IF NOT EXISTS idx_{p}{table}_lower_trim_email ON {p}{table} (lower(trim(email)))",
         f"{p}{table} lower(trim(email))"),
    ]


def _submission_table_indexes(prefix: str) -> list:
    """Lightweight indexes for cohort-prefixed submission / MCQ tables used by count queries."""
    p = prefix
    return [
        (f"CREATE INDEX IF NOT EXISTS idx_{p}skillboost_email ON {p}skillboost_profile(email)",
         f"{p}skillboost_profile email"),
        (f"CREATE INDEX IF NOT EXISTS idx_{p}skilllab_leader_email ON {p}skilllab_submission(leader_email)",
         f"{p}skilllab_submission leader_email"),
        (f"CREATE INDEX IF NOT EXISTS idx_{p}codelab_leader_email ON {p}codelab_submission(leader_email)",
         f"{p}codelab_submission leader_email"),
        (f"CREATE INDEX IF NOT EXISTS idx_{p}project_leader_email ON {p}project_submission(leader_email)",
         f"{p}project_submission leader_email"),
        (f"CREATE INDEX IF NOT EXISTS idx_{p}optional_mcq_track ON {p}optional_mcq_response(track_number)",
         f"{p}optional_mcq_response track_number"),
        (f"CREATE INDEX IF NOT EXISTS idx_{p}main_mcq_track ON {p}main_mcq_response(track_number)",
         f"{p}main_mcq_response track_number"),
    ]


def _cohort1_overlap_indexes() -> list:
    """Functional lower(trim(email)) indexes on Cohort 1 base tables.

    The Cohort 3 overlap CTE scans user_pii / user_pii_injected with LOWER(TRIM(email));
    plain email indexes can't serve that expression, so add functional ones.
    """
    return [
        ("CREATE INDEX IF NOT EXISTS idx_user_pii_lower_trim_email ON user_pii (lower(trim(email)))",
         "user_pii lower(trim(email))"),
        ("CREATE INDEX IF NOT EXISTS idx_user_pii_injected_lower_trim_email ON user_pii_injected (lower(trim(email)))",
         "user_pii_injected lower(trim(email))"),
    ]


def _build_index_list(prefixes, overlap_only=False) -> list:
    indexes = []
    # Cohort 1 base-table functional email indexes always help the Cohort 3 overlap query.
    indexes.extend(_cohort1_overlap_indexes())
    for prefix in prefixes:
        if overlap_only:
            indexes.append(
                (f"CREATE INDEX IF NOT EXISTS idx_{prefix}user_pii_lower_trim_email ON {prefix}user_pii (lower(trim(email)))",
                 f"{prefix}user_pii lower(trim(email))"),
            )
            indexes.append(
                (f"CREATE INDEX IF NOT EXISTS idx_{prefix}user_pii_injected_lower_trim_email ON {prefix}user_pii_injected (lower(trim(email)))",
                 f"{prefix}user_pii_injected lower(trim(email))"),
            )
            continue
        indexes.extend(_pii_table_indexes(prefix, "user_pii"))
        indexes.extend(_pii_table_indexes(prefix, "user_pii_injected"))
        indexes.extend(_submission_table_indexes(prefix))
    return indexes


def add_cohort_indexes(prefixes=None, overlap_only=False):
    load_dotenv()
    from server.config import Config

    prefixes = prefixes or DEFAULT_PREFIXES
    url = Config.SQLALCHEMY_DATABASE_URI
    print("add_cohort_indexes: using direct SQLAlchemy engine (full Flask app is NOT loaded).", flush=True)
    print(f"add_cohort_indexes: prefixes={prefixes} overlap_only={overlap_only}", flush=True)
    print("add_cohort_indexes: connecting (timeout 30s)…", flush=True)

    connect_args = {}
    if url.startswith("postgresql"):
        connect_args["connect_timeout"] = 30

    engine = create_engine(
        url,
        pool_pre_ping=True,
        pool_size=1,
        max_overflow=0,
        connect_args=connect_args,
    )

    indexes = _build_index_list(prefixes, overlap_only=overlap_only)
    n = len(indexes)

    successful = 0
    failed = 0

    with engine.connect() as conn:
        for i, (index_sql, description) in enumerate(indexes):
            print(f"[{i + 1}/{n}] {description} …", flush=True)
            try:
                conn.execute(text(index_sql))
                conn.commit()
                print("      [OK]", flush=True)
                successful += 1
            except Exception as e:
                conn.rollback()
                # Missing table (cohort not created yet) is expected — treat as non-fatal.
                print(f"      [FAILED] {e}", flush=True)
                failed += 1

    engine.dispose()
    print(f"\n[COMPLETE] {successful} ok, {failed} failed", flush=True)


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Create cohort-prefixed DB indexes (no Flask app startup).")
    p.add_argument(
        "--prefix",
        action="append",
        dest="prefixes",
        help="Cohort table prefix to index (repeatable). Default: cohort_2_ and cohort_3_.",
    )
    p.add_argument(
        "--overlap-only",
        action="store_true",
        help="Only create the lower(trim(email)) indexes used by the cross-cohort overlap query.",
    )
    args = p.parse_args()
    add_cohort_indexes(prefixes=args.prefixes, overlap_only=args.overlap_only)
