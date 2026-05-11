"""
Drop UNIQUE(track_number, email) on cohort_2_optional_mcq_response so Cohort 2 can store
multiple Optional MCQ submissions per leader email (track 4).

Run:
  python server/migrations/drop_cohort2_optional_mcq_unique_email.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from sqlalchemy import text

from server.app import create_app
from server.models import db


def run():
    app = create_app()
    with app.app_context():
        db.session.execute(
            text(
                "ALTER TABLE cohort_2_optional_mcq_response "
                "DROP CONSTRAINT IF EXISTS uq_cohort_2_optional_mcq_track_email"
            )
        )
        db.session.commit()
        print(
            "OK: dropped uq_cohort_2_optional_mcq_track_email on cohort_2_optional_mcq_response "
            "(if it existed)."
        )


if __name__ == "__main__":
    run()
