"""
Deduplicate Skill Lab submissions by (leader_email, upload_screenshot).

Run from project root:
  python scripts/repair_skilllab_submissions.py --dry-run
  python scripts/repair_skilllab_submissions.py --apply
  python scripts/repair_skilllab_submissions.py --apply --cohort 2
  python scripts/repair_skilllab_submissions.py --apply --all-cohorts
  python scripts/repair_skilllab_submissions.py --apply --add-unique-index

After --apply, re-import the source workbook to backfill any rows that were
never stored (skipped duplicates will not re-add existing email+link pairs).
"""
from __future__ import annotations

import argparse
import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from dotenv import load_dotenv

load_dotenv(os.path.join(project_root, ".env"))

from server.app import create_app
from server.models import db
from server.utils.skilllab_submission_repair import repair_skilllab_submission_duplicates
from sqlalchemy import text


COHORTS = {
    "1": ("", None),
    "2": ("cohort_2_", 2),
}


def _add_unique_indexes():
    """Prevent future duplicate email+link rows at the database level."""
    stmts = [
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_skilllab_submission_email_link
        ON skilllab_submission (
            lower(trim(leader_email)),
            lower(trim(coalesce(upload_screenshot, '')))
        )
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_cohort_2_skilllab_submission_email_link
        ON cohort_2_skilllab_submission (
            lower(trim(leader_email)),
            lower(trim(coalesce(upload_screenshot, '')))
        )
        """,
    ]
    with db.engine.connect() as conn:
        for sql in stmts:
            conn.execute(text(sql))
            conn.commit()
    print("OK unique indexes on (leader_email, upload_screenshot)")


def main():
    parser = argparse.ArgumentParser(description="Repair Skill Lab submission duplicates")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Delete duplicate rows (default is dry-run only)",
    )
    parser.add_argument(
        "--cohort",
        choices=("1", "2"),
        default="2",
        help="Cohort to repair (default: 2)",
    )
    parser.add_argument(
        "--all-cohorts",
        action="store_true",
        help="Repair cohort 1 and cohort 2",
    )
    parser.add_argument(
        "--add-unique-index",
        action="store_true",
        help="Create unique indexes after repair (run with --apply)",
    )
    args = parser.parse_args()
    dry_run = not args.apply

    app = create_app()
    with app.app_context():
        targets = list(COHORTS.items()) if args.all_cohorts else [(args.cohort, COHORTS[args.cohort])]

        for label, (prefix, cid) in targets:
            print(f"\n--- Cohort {label} ({prefix}skilllab_submission) ---")
            stats = repair_skilllab_submission_duplicates(
                prefix, cid, dry_run=dry_run,
            )
            for k, v in stats.items():
                print(f"  {k}: {v}")

        if args.add_unique_index:
            if dry_run:
                print("\nSkipping --add-unique-index (requires --apply)")
            else:
                _add_unique_indexes()

        if dry_run:
            print("\nDry run only. Re-run with --apply to delete duplicates.")
        else:
            try:
                from server.utils.cache import clear_cache
                clear_cache("_get_skilllab_submission_stats_cached")
            except Exception:
                pass
            print("\nDone. Refresh the Skill Lab Submissions page.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("Repair failed:", e)
        sys.exit(1)
