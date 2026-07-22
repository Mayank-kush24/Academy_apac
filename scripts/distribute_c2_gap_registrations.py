"""
Graph-only reshaping of the Cohort 2 Registration Trend.

The real data has a gap (no registrations) Jun 25 - Jul 1 2026 and a cluster of
~1,761 registrations on Jul 2-6. This script fills each of the 7 gap days with a
random 100-150 registrations by setting a graph-only ``display_registered_at`` on
a random subset of the Jul 2-6 users. The remaining users keep display_registered_at
NULL, so the chart shows them on their real Jul 2-6 dates.

IMPORTANT: real ``registered_at`` values are never modified. Only the graph-only
``display_registered_at`` override is written. Re-running is safe: it clears prior
overrides in the window first.

Run from project root:
    python scripts/distribute_c2_gap_registrations.py            # apply
    python scripts/distribute_c2_gap_registrations.py --dry-run  # preview only
"""
import argparse
import os
import random
from datetime import date, datetime, timedelta

import psycopg2

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

TABLE = "cohort_2_user_pii"
VIEW = "cohort_2_user_pii_combined"

# Real registrations occurred on these days; they form the pool to redistribute.
POOL_START = date(2026, 7, 2)
POOL_END = date(2026, 7, 7)  # exclusive upper bound (covers Jul 2-6)

# The empty days on the chart we want to fill.
GAP_DAYS = [
    date(2026, 6, 25),
    date(2026, 6, 26),
    date(2026, 6, 27),
    date(2026, 6, 28),
    date(2026, 6, 29),
    date(2026, 6, 30),
    date(2026, 7, 1),
]

PER_DAY_MIN = 100
PER_DAY_MAX = 150


def _random_datetime_on(day: date, rng: random.Random) -> datetime:
    """A random timestamp within the given day (looks natural, not all midnight)."""
    return datetime(day.year, day.month, day.day) + timedelta(
        seconds=rng.randint(0, 24 * 3600 - 1)
    )


def _print_series(cur, start: date, end: date) -> None:
    cur.execute(
        f"""SELECT DATE_TRUNC('day', COALESCE(display_registered_at, registered_at))::date AS d,
                   COUNT(*) AS n
            FROM {VIEW}
            WHERE COALESCE(display_registered_at, registered_at) >= %s
              AND COALESCE(display_registered_at, registered_at) < %s
            GROUP BY d ORDER BY d""",
        (start, end),
    )
    for d, n in cur.fetchall():
        print(f"  {d}  {n}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Distribute Cohort 2 gap registrations (graph only)")
    parser.add_argument("--seed", type=int, default=42, help="RNG seed (default 42, for reproducibility)")
    parser.add_argument("--dry-run", action="store_true", help="Show plan without writing")
    args = parser.parse_args()

    rng = random.Random(args.seed)

    url = os.environ["DATABASE_URL"]
    conn = psycopg2.connect(url)
    cur = conn.cursor()

    # Pool of candidate user ids (real registrations on Jul 2-6).
    cur.execute(
        f"""SELECT id FROM {TABLE}
            WHERE registered_at >= %s AND registered_at < %s""",
        (POOL_START, POOL_END),
    )
    pool = [r[0] for r in cur.fetchall()]
    rng.shuffle(pool)

    per_day = [rng.randint(PER_DAY_MIN, PER_DAY_MAX) for _ in GAP_DAYS]
    total_needed = sum(per_day)

    print(f"Pool size (real Jul {POOL_START.day}-{POOL_END.day - 1} registrations): {len(pool)}")
    print("Planned gap-day fill (100-150/day random):")
    for d, c in zip(GAP_DAYS, per_day):
        print(f"  {d}  <- {c}")
    print(f"Total moved to gap (graph only): {total_needed}")
    print(f"Left on real Jul dates: {len(pool) - total_needed}")

    if total_needed > len(pool):
        raise SystemExit(
            f"Not enough users in pool ({len(pool)}) to fill {total_needed}. "
            "Reduce per-day range or widen the pool window."
        )

    # Build (id, display_datetime) assignments.
    assignments: list[tuple[datetime, int]] = []
    idx = 0
    for day, count in zip(GAP_DAYS, per_day):
        for _ in range(count):
            uid = pool[idx]
            idx += 1
            assignments.append((_random_datetime_on(day, rng), uid))

    print("\nBEFORE (COALESCE series Jun 22 - Jul 6):")
    _print_series(cur, date(2026, 6, 22), date(2026, 7, 7))

    if args.dry_run:
        print("\n[DRY RUN] No changes written.")
        cur.close()
        conn.close()
        return

    # Idempotent: clear any prior overrides on the pool window first.
    cur.execute(
        f"""UPDATE {TABLE} SET display_registered_at = NULL
            WHERE registered_at >= %s AND registered_at < %s""",
        (POOL_START, POOL_END),
    )

    cur.executemany(
        f"UPDATE {TABLE} SET display_registered_at = %s WHERE id = %s",
        assignments,
    )
    conn.commit()
    print(f"\n[OK] Wrote {len(assignments)} display_registered_at overrides.")

    print("\nAFTER (COALESCE series Jun 22 - Jul 6):")
    _print_series(cur, date(2026, 6, 22), date(2026, 7, 7))

    # Safety check: real registered_at in the window is untouched.
    cur.execute(
        f"""SELECT COUNT(*) FROM {TABLE}
            WHERE registered_at >= %s AND registered_at < %s""",
        (POOL_START, POOL_END),
    )
    print(f"\n[verify] Real Jul 2-6 registered_at rows still present: {cur.fetchone()[0]}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
