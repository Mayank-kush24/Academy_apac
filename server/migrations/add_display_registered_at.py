"""
Add graph-only ``display_registered_at`` column to user_pii tables and recreate
user_pii_combined views so the Registration Trend chart can be reshaped without
touching the real ``registered_at`` dates.

The chart reads COALESCE(display_registered_at, registered_at); when the override
is NULL the real registration date is used, so this migration is a no-op for the
chart until display dates are populated (see scripts/distribute_c2_gap_registrations.py).

Run from project root:
    python server/migrations/add_display_registered_at.py            # cohort 2 (default)
    python server/migrations/add_display_registered_at.py --cohort 2
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
from server.utils.user_pii_combined_view import ensure_user_pii_combined_views  # noqa: E402


def _add_column(table: str) -> None:
    try:
        db.session.execute(
            text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS display_registered_at TIMESTAMP")
        )
        db.session.commit()
        print(f"[OK] {table}.display_registered_at")
    except Exception as e:
        db.session.rollback()
        if "already exists" not in str(e).lower():
            raise


def migrate_cohort(cohort_id: int) -> None:
    prefix = get_table_prefix(cohort_id)
    for base in ("user_pii", "user_pii_injected"):
        _add_column(f"{prefix}{base}")


def main():
    parser = argparse.ArgumentParser(description="Add display_registered_at column")
    parser.add_argument("--cohort", type=int, default=2, help="Cohort id (default: 2)")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        print(f"\n--- Cohort {args.cohort} ---")
        migrate_cohort(args.cohort)
        ensure_user_pii_combined_views(db.engine)
        print("\n[OK] user_pii_combined views refreshed")


if __name__ == "__main__":
    main()
