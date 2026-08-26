"""Export every participant email across cohorts 1-3 into a single CSV.

Reads the base tables directly (``{prefix}user_pii`` and ``{prefix}user_pii_injected``)
rather than the ``user_pii_combined`` views, so injected rows are picked up even when
a view is missing or stale. Emails are lowercased/trimmed and de-duplicated globally.
"""
import csv
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect as sa_inspect, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.cohort_config import ALLOWED_COHORT_IDS, get_table_prefix  # noqa: E402

OUTPUT = Path(__file__).resolve().parents[1] / "exports" / "all_cohorts_emails.csv"


def main() -> int:
    load_dotenv()
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("[ERROR] DATABASE_URL is not set")
        return 1

    engine = create_engine(database_url)
    existing_tables = set(sa_inspect(engine).get_table_names(schema="public"))

    emails: dict[str, None] = {}
    breakdown: list[tuple[str, int, int]] = []

    with engine.connect() as conn:
        for cohort_id in ALLOWED_COHORT_IDS:
            prefix = get_table_prefix(cohort_id)
            for suffix in ("user_pii", "user_pii_injected"):
                table = f"{prefix}{suffix}"
                if table not in existing_tables:
                    print(f"[SKIP] {table} does not exist")
                    continue
                rows = conn.execute(
                    text(
                        f"SELECT LOWER(TRIM(email)) AS email FROM {table} "
                        "WHERE email IS NOT NULL AND TRIM(email) <> ''"
                    )
                ).fetchall()
                before = len(emails)
                for (email,) in rows:
                    emails.setdefault(email, None)
                breakdown.append((table, len(rows), len(emails) - before))

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["email"])
        for email in sorted(emails):
            writer.writerow([email])

    for table, total, new in breakdown:
        print(f"{table:<34} rows={total:<7} new={new}")
    print(f"\nUnique emails: {len(emails)}")
    print(f"Written to: {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
