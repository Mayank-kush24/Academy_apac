"""
Add certificate_issued flag to user_pii / user_pii_injected for every cohort.

The flag records that a Certificate of Completion was generated for the
participant (source of truth: the certificate export CSV, loaded by
scripts/backfill_certificate_issued.py).

Run once:
  python server/migrations/add_certificate_issued.py
  python server/migrations/add_certificate_issued.py --cohort 2
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from sqlalchemy import inspect, text

from server.app import create_app
from server.cohort_config import ALLOWED_COHORT_IDS, get_table_prefix
from server.models import db
from server.utils.user_pii_combined_view import ensure_user_pii_combined_views

BASE_TABLES = ("user_pii", "user_pii_injected")


def _add_column(table: str) -> None:
    insp = inspect(db.engine)
    try:
        cols = {c["name"] for c in insp.get_columns(table)}
    except Exception:
        print(f"[SKIP] {table} (not present)")
        return
    if "certificate_issued" in cols:
        print(f"[SKIP] {table}.certificate_issued (already exists)")
        return
    db.session.execute(
        text(
            f"ALTER TABLE {table} "
            "ADD COLUMN certificate_issued BOOLEAN NOT NULL DEFAULT FALSE"
        )
    )
    print(f"[OK] {table}.certificate_issued added")


def run(cohort_ids) -> None:
    app = create_app()
    with app.app_context():
        for cid in cohort_ids:
            prefix = get_table_prefix(cid)
            for base in BASE_TABLES:
                _add_column(f"{prefix}{base}")
        db.session.commit()
        # View must be rebuilt so the new column reaches user_pii_combined.
        ensure_user_pii_combined_views(db.engine)
        print("Done: certificate_issued flag available.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cohort",
        type=int,
        action="append",
        choices=ALLOWED_COHORT_IDS,
        help="Cohort to migrate (repeatable). Default: all cohorts.",
    )
    args = parser.parse_args()
    run(args.cohort or list(ALLOWED_COHORT_IDS))
