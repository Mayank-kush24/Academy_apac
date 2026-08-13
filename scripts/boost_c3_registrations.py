"""
Placeholder registration top-up for the Cohort 3 dashboard.

Adds synthetic registrations per country to ``cohort_3_user_pii_injected``, which
the ``cohort_3_user_pii_combined`` view already unions into every dashboard query.
Real UTS-synced rows in ``cohort_3_user_pii`` are never read-modified or deleted.

Each synthetic row is cloned from a randomly sampled real row of the same country,
so state/city, registration date, UTM source, age and social-profile fields keep
their existing distribution shape and every derived chart scales coherently rather
than dumping thousands of NULLs into the "Other"/unknown buckets. Identity fields
(id, name, email) are freshly generated; ``bob_match`` is forced FALSE so the Book
of Business KPI stays tied to real data only.

Every generated email uses MARKER_DOMAIN, which makes the whole batch idempotent
(a re-run replaces it) and trivially reversible (``--revert`` deletes exactly it).

Run from project root:
    python scripts/boost_c3_registrations.py --dry-run   # preview, no writes
    python scripts/boost_c3_registrations.py             # apply
    python scripts/boost_c3_registrations.py --revert    # remove all seeded rows
"""
import argparse
import os
import random
from datetime import datetime, timezone
from uuid import uuid4

import psycopg2
from psycopg2.extras import execute_values

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

SRC_TABLE = "cohort_3_user_pii"
DST_TABLE = "cohort_3_user_pii_injected"
VIEW = "cohort_3_user_pii_combined"

MARKER_DOMAIN = "c3-seed.invalid"

# Extra registrations to add per country (not target totals).
BOOSTS: dict[str, int] = {
    "India": 5000,
    "China": 42,
    "Australia": 56,
    "South Korea": 210,
    "Malaysia": 57,
    "Sri Lanka": 500,
    "Japan": 34,
    "Nepal": 97,
    "Indonesia": 63,
    "Vietnam": 46,
    "Thailand": 92,
    "Bangladesh": 678,
    # "Other APAC" — 'APAC' is the canonical catch-all label the dashboard already
    # recognises for the APAC map, so these rows carry no state/city.
    "APAC": 125,
}

# Countries whose real rows are used as the cloning pool. 'APAC' has no real rows
# of its own, so it borrows the shape of every non-India APAC registration.
OTHER_APAC_KEY = "APAC"

# Cap on real rows pulled per country; a random sample this size approximates the
# country's true distribution closely enough for display purposes.
POOL_LIMIT = 5000

TEMPLATE_COLUMNS = [
    "registered_at", "organization_name", "class_stream", "domain", "designation",
    "state", "city", "date_of_birth", "gender", "occupation",
    "github_url", "linkedin_url", "utm_medium", "industry", "persona",
    "sub_category", "broad_category",
]

INSERT_COLUMNS = [
    "id", "registered_at", "organization_name", "class_stream", "domain",
    "designation", "name", "email", "mobile_number", "country", "state", "city",
    "date_of_birth", "gender", "occupation", "github_url", "linkedin_url",
    "utm_medium", "bob_match", "industry", "persona", "sub_category",
    "broad_category", "created_at", "updated_at",
]


def _country_counts(cur) -> dict[str, int]:
    cur.execute(
        f"""SELECT COALESCE(NULLIF(TRIM(country), ''), '(blank)'), COUNT(*)
            FROM {VIEW} GROUP BY 1"""
    )
    return {row[0]: int(row[1]) for row in cur.fetchall()}


def _fetch_pool(cur, country: str) -> list[tuple]:
    cols = ", ".join(TEMPLATE_COLUMNS)
    if country == OTHER_APAC_KEY:
        cur.execute(
            f"""SELECT {cols} FROM {SRC_TABLE}
                WHERE country IS NOT NULL AND TRIM(country) != ''
                  AND LOWER(TRIM(country)) != 'india'
                ORDER BY random() LIMIT %s""",
            (POOL_LIMIT,),
        )
    else:
        cur.execute(
            f"""SELECT {cols} FROM {SRC_TABLE}
                WHERE LOWER(TRIM(country)) = %s
                ORDER BY random() LIMIT %s""",
            (country.lower(), POOL_LIMIT),
        )
    return cur.fetchall()


def _build_rows(country: str, count: int, pool: list[tuple], rng: random.Random,
                seq_start: int, now: datetime) -> list[tuple]:
    idx = {name: i for i, name in enumerate(TEMPLATE_COLUMNS)}
    drop_location = country == OTHER_APAC_KEY
    rows = []
    for offset in range(count):
        seq = seq_start + offset
        tpl = rng.choice(pool)
        handle = f"c3seed{seq:06d}"
        rows.append((
            str(uuid4()),
            tpl[idx["registered_at"]],
            tpl[idx["organization_name"]],
            tpl[idx["class_stream"]],
            tpl[idx["domain"]],
            tpl[idx["designation"]],
            f"Participant {seq:06d}",
            f"{handle}@{MARKER_DOMAIN}",
            None,
            country,
            None if drop_location else tpl[idx["state"]],
            None if drop_location else tpl[idx["city"]],
            tpl[idx["date_of_birth"]],
            tpl[idx["gender"]],
            tpl[idx["occupation"]],
            f"https://github.com/{handle}" if tpl[idx["github_url"]] else None,
            f"https://www.linkedin.com/in/{handle}" if tpl[idx["linkedin_url"]] else None,
            tpl[idx["utm_medium"]],
            False,
            tpl[idx["industry"]],
            tpl[idx["persona"]],
            tpl[idx["sub_category"]],
            tpl[idx["broad_category"]],
            now,
            now,
        ))
    return rows


def _delete_seeded(cur) -> int:
    cur.execute(f"DELETE FROM {DST_TABLE} WHERE email LIKE %s", (f"%@{MARKER_DOMAIN}",))
    return cur.rowcount


def main() -> None:
    parser = argparse.ArgumentParser(description="Top up Cohort 3 registrations for display")
    parser.add_argument("--seed", type=int, default=42, help="RNG seed (default 42, reproducible)")
    parser.add_argument("--dry-run", action="store_true", help="Show plan without writing")
    parser.add_argument("--revert", action="store_true", help="Delete previously seeded rows and exit")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()

    before = _country_counts(cur)

    if args.revert:
        removed = _delete_seeded(cur)
        conn.commit()
        print(f"[OK] Removed {removed} seeded rows from {DST_TABLE}.")
        after = _country_counts(cur)
        print(f"Cohort 3 total registrations: {sum(before.values())} -> {sum(after.values())}")
        cur.close()
        conn.close()
        return

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    all_rows: list[tuple] = []
    seq = 1
    print(f"{'Country':<16} {'current':>9} {'+add':>7} {'new':>9}   pool")
    for country, count in BOOSTS.items():
        pool = _fetch_pool(cur, country)
        if not pool:
            raise SystemExit(f"No real rows available to clone for '{country}'.")
        all_rows.extend(_build_rows(country, count, pool, rng, seq, now))
        seq += count
        current = before.get(country, 0)
        print(f"{country:<16} {current:>9} {count:>+7} {current + count:>9}   {len(pool)}")

    total_before = sum(before.values())
    print(f"\nRows to insert: {len(all_rows)}")
    print(f"Cohort 3 total registrations: {total_before} -> {total_before + len(all_rows)}")

    if args.dry_run:
        print("\n[DRY RUN] No changes written.")
        cur.close()
        conn.close()
        return

    removed = _delete_seeded(cur)
    if removed:
        print(f"\nCleared {removed} rows from a previous run (idempotent re-seed).")

    execute_values(
        cur,
        f"INSERT INTO {DST_TABLE} ({', '.join(INSERT_COLUMNS)}) VALUES %s",
        all_rows,
        page_size=1000,
    )
    conn.commit()
    print(f"\n[OK] Inserted {len(all_rows)} rows into {DST_TABLE}.")

    after = _country_counts(cur)
    print("\nAFTER (per-country registrations in the dashboard view):")
    for country in BOOSTS:
        print(f"  {country:<16} {before.get(country, 0):>7} -> {after.get(country, 0):>7}")
    print(f"\nTotal: {total_before} -> {sum(after.values())}")

    cur.execute(f"SELECT COUNT(*) FROM {SRC_TABLE}")
    print(f"[verify] Real {SRC_TABLE} rows untouched: {cur.fetchone()[0]}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
