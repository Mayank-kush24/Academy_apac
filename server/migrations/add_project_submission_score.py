"""
Add score to project_submission (public + cohort_2_).

Run once:
  python server/migrations/add_project_submission_score.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from sqlalchemy import inspect, text

from server.app import create_app
from server.models import db


def _ensure_column(table: str):
    insp = inspect(db.engine)
    try:
        cols = {c["name"] for c in insp.get_columns(table)}
    except Exception:
        return
    if "score" in cols:
        return
    db.session.execute(text(f"ALTER TABLE {table} ADD COLUMN score NUMERIC(10, 2)"))


def run():
    app = create_app()
    with app.app_context():
        for tbl in ("project_submission", "cohort_2_project_submission"):
            _ensure_column(tbl)
        db.session.commit()
        print("OK: score column ensured on project_submission tables.")


if __name__ == "__main__":
    run()
