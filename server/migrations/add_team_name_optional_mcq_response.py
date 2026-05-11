"""
Add team_name to optional_mcq_response (public + cohort_2_).

Run once against your database:
  python server/migrations/add_team_name_optional_mcq_response.py
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
    if "team_name" in cols:
        return
    db.session.execute(text(f"ALTER TABLE {table} ADD COLUMN team_name VARCHAR(512)"))


def run():
    app = create_app()
    with app.app_context():
        for tbl in ("optional_mcq_response", "cohort_2_optional_mcq_response"):
            _ensure_column(tbl)
        db.session.commit()
        print("OK: team_name column ensured on optional_mcq_response tables.")


if __name__ == "__main__":
    run()
