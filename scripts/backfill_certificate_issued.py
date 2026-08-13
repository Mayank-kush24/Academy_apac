"""
Flag participants whose Certificate of Completion has been issued, from a
certificate export CSV (columns: certificateId, recipientName, recipientEmail,
typeName, status).

Sets user_pii.certificate_issued / user_pii_injected.certificate_issued = TRUE
for every email present in the CSV, matching case-insensitively.

Usage:
  python scripts/backfill_certificate_issued.py <csv> --cohort 2            # dry run
  python scripts/backfill_certificate_issued.py <csv> --cohort 2 --apply
  python scripts/backfill_certificate_issued.py <csv> --cohort 2 --apply --sync

--sync additionally clears the flag for participants absent from the CSV, which
is only correct when the CSV is a complete export for the cohort.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv()

BASE_TABLES = ("user_pii", "user_pii_injected")


def read_emails(csv_path: Path) -> list[str]:
    with csv_path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if "recipientEmail" not in (reader.fieldnames or []):
            raise SystemExit(
                f"{csv_path}: missing 'recipientEmail' column (found: {reader.fieldnames})"
            )
        emails = {
            (row.get("recipientEmail") or "").strip().lower()
            for row in reader
        }
    emails.discard("")
    return sorted(emails)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("csv", type=Path, help="Certificate export CSV")
    ap.add_argument("--cohort", type=int, default=2)
    ap.add_argument("--apply", action="store_true", help="Commit changes")
    ap.add_argument(
        "--sync",
        action="store_true",
        help="Also clear the flag for participants not in the CSV",
    )
    args = ap.parse_args()

    emails = read_emails(args.csv)
    print(f"CSV: {args.csv}  ->  {len(emails)} unique recipient emails")

    from sqlalchemy import text

    from server.app import create_app
    from server.cohort_config import get_table_prefix
    from server.models import db

    prefix = get_table_prefix(args.cohort)
    app = create_app()
    with app.app_context():
        totals = {"set": 0, "cleared": 0}
        for base in BASE_TABLES:
            table = f"{prefix}{base}"
            matched = db.session.execute(
                text(f"SELECT COUNT(*) FROM {table} WHERE lower(email) = ANY(:emails)"),
                {"emails": emails},
            ).scalar_one()
            to_set = db.session.execute(
                text(
                    f"SELECT COUNT(*) FROM {table} "
                    "WHERE lower(email) = ANY(:emails) AND certificate_issued IS NOT TRUE"
                ),
                {"emails": emails},
            ).scalar_one()
            to_clear = db.session.execute(
                text(
                    f"SELECT COUNT(*) FROM {table} "
                    "WHERE NOT (lower(email) = ANY(:emails)) AND certificate_issued IS TRUE"
                ),
                {"emails": emails},
            ).scalar_one()

            print(
                f"  {table}: {matched} rows match the CSV, "
                f"{to_set} need the flag set, {to_clear} carry a stale flag"
            )
            totals["set"] += to_set
            totals["cleared"] += to_clear if args.sync else 0

            if args.apply:
                db.session.execute(
                    text(
                        f"UPDATE {table} SET certificate_issued = TRUE, updated_at = NOW() "
                        "WHERE lower(email) = ANY(:emails) AND certificate_issued IS NOT TRUE"
                    ),
                    {"emails": emails},
                )
                if args.sync:
                    db.session.execute(
                        text(
                            f"UPDATE {table} SET certificate_issued = FALSE, updated_at = NOW() "
                            "WHERE NOT (lower(email) = ANY(:emails)) AND certificate_issued IS TRUE"
                        ),
                        {"emails": emails},
                    )

        # An email can sit in both base tables, so count distinct addresses.
        distinct_matched = db.session.execute(
            text(
                f"SELECT COUNT(*) FROM ("
                f"  SELECT lower(email) FROM {prefix}user_pii WHERE lower(email) = ANY(:emails)"
                f"  UNION"
                f"  SELECT lower(email) FROM {prefix}user_pii_injected WHERE lower(email) = ANY(:emails)"
                f") t"
            ),
            {"emails": emails},
        ).scalar_one()
        print(
            f"Total: {distinct_matched} of {len(emails)} CSV emails matched a cohort "
            f"{args.cohort} participant, {len(emails) - distinct_matched} unmatched"
        )

        if args.apply:
            db.session.commit()
            print(f"Applied: {totals['set']} flagged, {totals['cleared']} cleared.")
        else:
            db.session.rollback()
            print("Dry run - nothing written. Re-run with --apply.")


if __name__ == "__main__":
    main()
