"""
Revert Cohort 3 rows that were written into the Cohort 1 (public) tables.

A sync invoked outside a request context resolved g.table_prefix to "" and imported
Cohort 3 registrations and modules into the unprefixed tables. This removes the rows
that run inserted and recomputes cohort 1 bob_match.

Rows that existed before the run and were *overwritten* cannot be restored here;
they are only reported.

Usage:
  python scripts/revert_misscoped_c3_import.py                 # dry run
  python scripts/revert_misscoped_c3_import.py --apply
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from sqlalchemy import text

from server.app import create_app
from server.models import db
from server.utils.bob_match import recalculate_bob_match_with_prefix

# The mis-scoped run wrote everything inside this one-minute window.
WINDOW_START = "2026-07-28 06:37:00"
WINDOW_END = "2026-07-28 06:38:00"

# Children before parents: both reference user_pii(email).
#
# user_pii and skillboost_profile stamp created_at with utcnow, so the run window
# identifies them. skilllab_submission carries created_at through from the source
# submission, so that row is matched on its own identity instead.
DELETE_TARGETS = (
    (
        "skilllab_submission",
        "leader_email = :sl_email AND created_at = :sl_created",
        {"sl_email": "dhitihamu2@gmail.com", "sl_created": "2026-07-28 13:18:08.918000"},
    ),
    ("skillboost_profile", "created_at >= :s AND created_at < :e", {}),
    ("user_pii", "created_at >= :s AND created_at < :e", {}),
)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--start", default=WINDOW_START)
    ap.add_argument("--end", default=WINDOW_END)
    args = ap.parse_args()

    bounds = {"s": args.start, "e": args.end}

    app = create_app()
    with app.app_context():
        print(f"window: {args.start} .. {args.end}\n")

        for tbl, where, extra in DELETE_TARGETS:
            n = db.session.execute(
                text(f"SELECT COUNT(*) FROM {tbl} WHERE {where}"), {**bounds, **extra}
            ).scalar()
            print(f"  {tbl:22s} rows to delete: {n}")

        overwritten = db.session.execute(
            text(
                "SELECT COUNT(*) FROM user_pii "
                "WHERE updated_at >= :s AND updated_at < :e AND created_at < :s"
            ),
            bounds,
        ).scalar()
        print(f"\n  user_pii rows OVERWRITTEN (not restorable here): {overwritten}")

        if not args.apply:
            print("\nDry run. Re-run with --apply to delete.")
            return

        print()
        for tbl, where, extra in DELETE_TARGETS:
            res = db.session.execute(
                text(f"DELETE FROM {tbl} WHERE {where}"), {**bounds, **extra}
            )
            print(f"  [OK] deleted {res.rowcount} from {tbl}")
        db.session.commit()

        changed = recalculate_bob_match_with_prefix("")
        print(f"  [OK] cohort 1 bob_match recomputed ({changed} rows changed)")


if __name__ == "__main__":
    main()
