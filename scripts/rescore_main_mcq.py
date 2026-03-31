#!/usr/bin/env python3
"""
Re-score all Main MCQ (MCQ Verification) submissions using the current ANSWER_KEY.
Use after updating server/utils/main_mcq_answer_key.py so existing rows get new scores.

Usage (from project root):
  python scripts/rescore_main_mcq.py
"""
import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


def main():
    from server.app import create_app
    from server.models import db, MainMcqResponse
    from server.utils.main_mcq_answer_key import score_submission

    app = create_app()
    with app.app_context():
        rows = MainMcqResponse.query.all()
        total = len(rows)
        if total == 0:
            print("No Main MCQ submissions found. Nothing to rescore.")
            return

        updated = 0
        batch = 0
        batch_size = 100
        for r in rows:
            result = score_submission(
                r.track_number,
                r.question_1, r.question_2, r.question_3, r.question_4,
                r.question_5, r.question_6, r.question_7, r.question_8,
                r.question_9, r.question_10,
            )
            new_score = result["correct_count"]
            if r.score != new_score:
                r.score = new_score
                updated += 1
            batch += 1
            if batch >= batch_size:
                db.session.commit()
                batch = 0

        if batch > 0:
            db.session.commit()

        print(f"Rescored {total} Main MCQ submission(s). Updated score for {updated} row(s).")


if __name__ == "__main__":
    main()
