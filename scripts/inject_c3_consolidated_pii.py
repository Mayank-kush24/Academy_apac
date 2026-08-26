"""
Inject the consolidated PII list into the Cohort 3 injected participants table.

Source: "Data Consolidation - Can be Injected.csv" (7,257 rows, all unique emails).
Target: cohort_3_user_pii_injected

The table currently holds 7,000 synthetic placeholder rows written by
scripts/boost_c3_registrations.py (emails ending @c3-seed.invalid). Those are
deleted first so the real records replace them; pass --keep-seeds to keep them.

registered_at is spread randomly across Aug 4-12 2026 (9 days). Per-day counts
are randomised around the mean (7257 / 9 = 806) rather than being flat, and each
row gets a random time of day so the Registration Trend chart looks organic.
display_registered_at is left NULL: these rows have no real date to preserve, so
the chart reads registered_at directly.

Rows are skipped (not failed) when the email already exists in cohort_3_user_pii
or cohort_3_user_pii_injected, so re-running never creates duplicates.

Run from project root:
    python scripts/inject_c3_consolidated_pii.py --dry-run   # preview only
    python scripts/inject_c3_consolidated_pii.py             # apply
"""
import argparse
import csv
import os
import random
import sys
from datetime import date, datetime, timedelta, timezone

import psycopg2
from psycopg2.extras import execute_values

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from server.utils.title_map import get_title_categories  # noqa: E402

TABLE = "cohort_3_user_pii_injected"
REAL_TABLE = "cohort_3_user_pii"
BOB_TABLE = "cohort_3_bob_companies"
VIEW = "cohort_3_user_pii_combined"

DEFAULT_CSV = "Data Consolidation - Can be Injected.csv"
SEED_EMAIL_LIKE = "%@c3-seed.invalid"

WINDOW_START = date(2026, 8, 4)
WINDOW_END = date(2026, 8, 13)  # exclusive, so Aug 4-12 inclusive = 9 days

# Per-day counts are drawn from this multiplier band around the mean.
DAY_WEIGHT_MIN = 0.75
DAY_WEIGHT_MAX = 1.25

# CSV header -> (db column, max length or None for non-varchar)
FIELD_MAP = [
    ("Name", "name", 255),
    ("Title", "designation", 255),
    ("Company", "organization_name", 255),
    ("Email", "email", 255),
    ("Phone", "mobile_number", 50),
    ("LinkedIn", "linkedin_url", 500),
    ("City", "city", 100),
    ("State", "state", 100),
    ("Country", "country", 100),
    ("Class/Stream", "class_stream", 255),
    ("Domain", "domain", 255),
    ("Gender", "gender", 50),
    ("Occupation", "occupation", 255),
    ("utm_medium", "utm_medium", 255),
]

INSERT_COLUMNS = [
    "registered_at",
    "name",
    "designation",
    "organization_name",
    "email",
    "mobile_number",
    "linkedin_url",
    "city",
    "state",
    "country",
    "class_stream",
    "domain",
    "gender",
    "occupation",
    "utm_medium",
    "date_of_birth",
    "bob_match",
    "sub_category",
    "broad_category",
    "created_at",
    "updated_at",
]

# Recompute bob_match for the injected table only (same semantics as
# server/utils/bob_match.py, inlined so the script needs no Flask app context).
BOB_MATCH_SQL = f"""
WITH computed AS (
    SELECT u.id AS uid,
        (
            btrim(COALESCE(u.organization_name, '')) <> ''
            AND EXISTS (
                SELECT 1 FROM {BOB_TABLE} AS b
                WHERE lower(btrim(COALESCE(u.organization_name, ''))) = lower(btrim(
                    CASE
                        WHEN b.normalized_name IS NOT NULL AND btrim(b.normalized_name) <> ''
                            THEN b.normalized_name
                        ELSE COALESCE(b.company_name, '')
                    END
                ))
            )
        ) AS new_bm
    FROM {TABLE} AS u
)
UPDATE {TABLE} AS u
SET bob_match = c.new_bm
FROM computed AS c
WHERE u.id = c.uid AND u.bob_match IS DISTINCT FROM c.new_bm
"""


def _clean(value, max_len=None):
    """Blank-to-NULL, trimmed, and clipped to the column width."""
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    if max_len is not None and len(value) > max_len:
        value = value[:max_len]
    return value


def _parse_dob(value):
    """Source dates of birth are dd-mm-yyyy; anything else is dropped rather than guessed."""
    value = (value or "").strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%d-%m-%Y").date()
    except ValueError:
        return None


def _days_in_window():
    days = []
    d = WINDOW_START
    while d < WINDOW_END:
        days.append(d)
        d += timedelta(days=1)
    return days


def _allocate_per_day(total, days, rng):
    """Random per-day counts summing exactly to total (largest-remainder rounding)."""
    weights = [rng.uniform(DAY_WEIGHT_MIN, DAY_WEIGHT_MAX) for _ in days]
    scale = total / sum(weights)
    raw = [w * scale for w in weights]
    counts = [int(x) for x in raw]

    shortfall = total - sum(counts)
    order = sorted(range(len(days)), key=lambda i: raw[i] - counts[i], reverse=True)
    for i in range(shortfall):
        counts[order[i]] += 1
    return counts


def _random_datetime_on(day, rng):
    """A random timestamp within the given day, so rows are not all at midnight."""
    return datetime(day.year, day.month, day.day) + timedelta(seconds=rng.randint(0, 24 * 3600 - 1))


def _print_series(cur, start, end, label):
    cur.execute(
        f"""SELECT DATE_TRUNC('day', COALESCE(display_registered_at, registered_at))::date AS d,
                   COUNT(*) AS n
            FROM {VIEW}
            WHERE COALESCE(display_registered_at, registered_at) >= %s
              AND COALESCE(display_registered_at, registered_at) < %s
            GROUP BY d ORDER BY d""",
        (start, end),
    )
    rows = cur.fetchall()
    print(f"\n{label} (combined view, {start} to {end - timedelta(days=1)}):")
    for d, n in rows:
        print(f"  {d}  {n}")
    print(f"  total: {sum(n for _, n in rows)}")


def load_csv(path):
    """Read the CSV into insert-ready dicts, dropping blank/duplicate emails."""
    records = []
    skipped_no_email = 0
    dupes_in_file = 0
    seen = set()

    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            email = _clean(row.get("Email"), 255)
            if not email:
                skipped_no_email += 1
                continue
            key = email.lower()
            if key in seen:
                dupes_in_file += 1
                continue
            seen.add(key)

            rec = {db_col: _clean(row.get(src), max_len) for src, db_col, max_len in FIELD_MAP}
            rec["email"] = email
            rec["date_of_birth"] = _parse_dob(row.get("Date of birth"))
            records.append(rec)

    return records, skipped_no_email, dupes_in_file


def main():
    parser = argparse.ArgumentParser(description="Inject consolidated PII into Cohort 3 injected table")
    parser.add_argument("--csv", default=DEFAULT_CSV, help=f"Source CSV (default: {DEFAULT_CSV})")
    parser.add_argument("--seed", type=int, default=42, help="RNG seed for reproducibility (default 42)")
    parser.add_argument("--keep-seeds", action="store_true", help="Keep the @c3-seed.invalid placeholder rows")
    parser.add_argument("--dry-run", action="store_true", help="Show the plan without writing")
    args = parser.parse_args()

    rng = random.Random(args.seed)

    records, skipped_no_email, dupes_in_file = load_csv(args.csv)
    print(f"CSV: {args.csv}")
    print(f"  usable rows: {len(records)}")
    print(f"  skipped (blank email): {skipped_no_email}")
    print(f"  skipped (duplicate email in file): {dupes_in_file}")

    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()

    _print_series(cur, WINDOW_START - timedelta(days=10), WINDOW_END, "BEFORE")

    cur.execute(f"SELECT COUNT(*) FROM {TABLE} WHERE email LIKE %s", (SEED_EMAIL_LIKE,))
    seed_count = cur.fetchone()[0]
    print(f"\nPlaceholder seed rows in {TABLE}: {seed_count}")
    print("  action: " + ("KEEP (--keep-seeds)" if args.keep_seeds else "DELETE"))

    # Emails that would block an insert. Seed rows are excluded when they are about
    # to be deleted, so a seed address never suppresses a real record.
    seed_filter = "" if args.keep_seeds else f" WHERE email NOT LIKE '{SEED_EMAIL_LIKE}'"
    cur.execute(
        f"SELECT LOWER(email) FROM {REAL_TABLE}"
        f" UNION SELECT LOWER(email) FROM {TABLE}{seed_filter}"
    )
    existing = {r[0] for r in cur.fetchall() if r[0]}

    fresh = [r for r in records if r["email"].lower() not in existing]
    already = len(records) - len(fresh)
    print(f"\nAlready present in cohort 3 (skipped): {already}")
    print(f"To insert: {len(fresh)}")

    if not fresh:
        print("\nNothing to insert.")
        cur.close()
        conn.close()
        return

    days = _days_in_window()
    per_day = _allocate_per_day(len(fresh), days, rng)
    print(
        f"\nDate spread across {len(days)} days "
        f"({WINDOW_START} to {WINDOW_END - timedelta(days=1)}), mean {len(fresh) / len(days):.0f}/day:"
    )
    for d, c in zip(days, per_day):
        print(f"  {d}  <- {c}")

    # Shuffle first: the CSV is grouped by country, so sequential assignment would
    # make each day a single-country block.
    rng.shuffle(fresh)

    # created_at/updated_at are TIMESTAMP WITHOUT TIME ZONE, so store naive UTC.
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    values = []
    idx = 0
    # Injected rows bypass the importer, so classify designations here too; otherwise
    # they land in the dashboard's Unclassified bucket despite carrying a real title.
    category_cache: dict[str, tuple] = {}
    for day, count in zip(days, per_day):
        for _ in range(count):
            rec = fresh[idx]
            idx += 1
            designation = rec["designation"]
            if designation not in category_cache:
                category_cache[designation] = get_title_categories(designation)
            sub_category, broad_category = category_cache[designation]
            values.append(
                (
                    _random_datetime_on(day, rng),
                    rec["name"],
                    rec["designation"],
                    rec["organization_name"],
                    rec["email"],
                    rec["mobile_number"],
                    rec["linkedin_url"],
                    rec["city"],
                    rec["state"],
                    rec["country"],
                    rec["class_stream"],
                    rec["domain"],
                    rec["gender"],
                    rec["occupation"],
                    rec["utm_medium"],
                    rec["date_of_birth"],
                    False,
                    sub_category,
                    broad_category,
                    now,
                    now,
                )
            )

    if args.dry_run:
        print("\n[DRY RUN] No changes written.")
        cur.close()
        conn.close()
        return

    if not args.keep_seeds:
        cur.execute(f"DELETE FROM {TABLE} WHERE email LIKE %s", (SEED_EMAIL_LIKE,))
        print(f"\n[OK] Deleted {cur.rowcount} placeholder seed row(s).")

    execute_values(
        cur,
        f"INSERT INTO {TABLE} ({', '.join(INSERT_COLUMNS)}) VALUES %s",
        values,
        page_size=1000,
    )
    print(f"[OK] Inserted {len(values)} row(s).")

    cur.execute(BOB_MATCH_SQL)
    print(f"[OK] Recalculated bob_match ({cur.rowcount} row(s) changed).")

    conn.commit()

    cur.execute(f"SELECT COUNT(*) FROM {TABLE}")
    print(f"\n[verify] {TABLE} now holds {cur.fetchone()[0]} row(s).")
    cur.execute(f"SELECT bob_match, COUNT(*) FROM {TABLE} GROUP BY 1 ORDER BY 1")
    print(f"[verify] bob_match: {dict(cur.fetchall())}")

    _print_series(cur, WINDOW_START - timedelta(days=10), WINDOW_END, "AFTER")

    cur.close()
    conn.close()
    print("\nDone. Restart the server (or wait for the cache TTL) to refresh the dashboard.")


if __name__ == "__main__":
    main()
