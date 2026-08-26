"""
Add sub_category and broad_category to user_pii tables, backfill from designation (Cohort 2),
and recreate user_pii_combined views.

Run from project root:
    python server/migrations/add_title_category_columns.py
    python server/migrations/add_title_category_columns.py --cohort 2
"""
import argparse
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from sqlalchemy import text  # noqa: E402

from server.app import create_app  # noqa: E402
from server.cohort_config import get_table_prefix  # noqa: E402
from server.models import db  # noqa: E402
from server.utils.title_map import get_title_categories  # noqa: E402
from server.utils.user_pii_combined_view import ensure_user_pii_combined_views  # noqa: E402


def _add_columns(table: str) -> None:
    for col, typ in (("sub_category", "VARCHAR(255)"), ("broad_category", "VARCHAR(100)")):
        try:
            db.session.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {typ}"))
            db.session.commit()
            print(f"[OK] {table}.{col}")
        except Exception as e:
            db.session.rollback()
            if "already exists" not in str(e).lower():
                raise


def _backfill_table(table: str, only_missing: bool = False) -> int:
    # Rows inserted outside the importer (e.g. the PII injection script) carry a real
    # designation but no categories, so they show up as Unclassified. only_missing
    # fills just those and leaves existing classifications untouched.
    missing_sql = (
        " AND (broad_category IS NULL OR TRIM(broad_category) = '')" if only_missing else ""
    )
    rows = db.session.execute(
        text(
            f"SELECT id, designation FROM {table} "
            f"WHERE designation IS NOT NULL AND TRIM(designation) != ''{missing_sql}"
        )
    ).fetchall()
    print(f"Backfilling {len(rows)} rows in {table}...")
    desig_cache: dict[str, tuple] = {}
    batch = []
    updated = 0
    for row_id, designation in rows:
        if designation not in desig_cache:
            desig_cache[designation] = get_title_categories(designation)
        sub, broad = desig_cache[designation]
        batch.append({"rid": row_id, "sub": sub, "broad": broad})
        if len(batch) >= 1000:
            db.session.execute(
                text(
                    f"UPDATE {table} SET sub_category = :sub, broad_category = :broad WHERE id = :rid"
                ),
                batch,
            )
            db.session.commit()
            updated += len(batch)
            batch = []
    if batch:
        db.session.execute(
            text(f"UPDATE {table} SET sub_category = :sub, broad_category = :broad WHERE id = :rid"),
            batch,
        )
        db.session.commit()
        updated += len(batch)
    print(f"[OK] Backfilled {updated} rows in {table} ({len(desig_cache)} unique designations)")
    return updated


def migrate_cohort(cohort_id: int, backfill: bool, only_missing: bool = False) -> None:
    prefix = get_table_prefix(cohort_id)
    for base in ("user_pii", "user_pii_injected"):
        _add_columns(f"{prefix}{base}")
    if backfill and cohort_id in (2, 3):
        for base in ("user_pii", "user_pii_injected"):
            _backfill_table(f"{prefix}{base}", only_missing=only_missing)


def main():
    parser = argparse.ArgumentParser(description="Add title category columns and optional backfill")
    parser.add_argument("--cohort", type=int, default=None, help="Cohort id (default: 1 and 2)")
    parser.add_argument("--no-backfill", action="store_true", help="Skip designation backfill")
    parser.add_argument(
        "--only-missing",
        action="store_true",
        help="Classify only rows with no category yet, leaving existing ones untouched",
    )
    args = parser.parse_args()

    cohorts = [args.cohort] if args.cohort is not None else [1, 2]
    app = create_app()
    with app.app_context():
        for cid in cohorts:
            print(f"\n--- Cohort {cid} ---")
            migrate_cohort(cid, backfill=not args.no_backfill, only_missing=args.only_missing)
        ensure_user_pii_combined_views(db.engine)
        print("\n[OK] user_pii_combined views refreshed")


if __name__ == "__main__":
    main()
