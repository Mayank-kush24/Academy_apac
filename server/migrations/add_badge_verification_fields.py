"""
Add completion_date and last_verified_at to skilllab_submission and codelab_submission
(public + cohort_2_).

Run once:
  python server/migrations/add_badge_verification_fields.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from sqlalchemy import inspect, text

from server.app import create_app
from server.models import db


def _ensure_columns(table: str):
    insp = inspect(db.engine)
    try:
        cols = {c["name"] for c in insp.get_columns(table)}
    except Exception:
        return
    stmts = []
    if "completion_date" not in cols:
        stmts.append(f"ALTER TABLE {table} ADD COLUMN completion_date TIMESTAMP NULL")
    if "last_verified_at" not in cols:
        stmts.append(f"ALTER TABLE {table} ADD COLUMN last_verified_at TIMESTAMP NULL")
    for stmt in stmts:
        db.session.execute(text(stmt))


def run():
    app = create_app()
    with app.app_context():
        for tbl in (
            "skilllab_submission",
            "codelab_submission",
            "cohort_2_skilllab_submission",
            "cohort_2_codelab_submission",
            "cohort_3_skilllab_submission",
            "cohort_3_codelab_submission",
        ):
            _ensure_columns(tbl)
        db.session.commit()
        print("OK: completion_date / last_verified_at ensured on submission tables.")


if __name__ == "__main__":
    run()
