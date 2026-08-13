"""
Widen bob_companies.company_name / normalized_name from VARCHAR(500) to VARCHAR(1000).

Run once:
  python server/migrations/widen_bob_company_name.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from sqlalchemy import inspect, text

from server.app import create_app
from server.models import db

NEW_LENGTH = 1000
COLUMNS = ("company_name", "normalized_name")
TABLES = ("bob_companies", "cohort_2_bob_companies", "cohort_3_bob_companies")


def _widen(table: str) -> None:
    insp = inspect(db.engine)
    try:
        cols = {c["name"]: c for c in insp.get_columns(table)}
    except Exception:
        print(f"[SKIP] {table} (not present)")
        return
    for col in COLUMNS:
        if col not in cols:
            continue
        db.session.execute(
            text(f"ALTER TABLE {table} ALTER COLUMN {col} TYPE VARCHAR({NEW_LENGTH})")
        )
        print(f"[OK] {table}.{col} -> VARCHAR({NEW_LENGTH})")


def run():
    app = create_app()
    with app.app_context():
        for tbl in TABLES:
            _widen(tbl)
        db.session.commit()
        print("Done: bob_companies name columns widened.")


if __name__ == "__main__":
    run()
