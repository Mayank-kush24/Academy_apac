"""
Advance the UTS registration watermark past a record the upstream API cannot serve.

The Hack2Skill registrations endpoint aggregates with a $convert to ObjectId; when a
record holds a non-ObjectId value in that field the whole cursor dies with HTTP 500,
so every window containing it is unfetchable. There is no end-of-range parameter, so
the only way forward is to start after the bad record and record the skipped window
as a gap.

Finds the earliest safe ``start`` by probing the live API, then stores it.

Usage:
  python scripts/skip_uts_poisoned_window.py                  # probe, show plan, no writes
  python scripts/skip_uts_poisoned_window.py --apply
  python scripts/skip_uts_poisoned_window.py --apply --start 2026-07-26T15:21:04Z
"""
import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from server.app import create_app
from server.utils.h2s_uts_client import H2SUtsClient, H2SUtsError
from server.utils.h2s_uts_sync import (
    SYNC_KEY_REGISTRATION_START,
    add_registration_gap,
    get_registration_gaps,
    get_sync_value,
    set_sync_value,
)

ISO_FMT = "%Y-%m-%dT%H:%M:%S.000Z"


def _iso(dt: datetime) -> str:
    return dt.strftime(ISO_FMT)


def _parse_iso(value: str) -> datetime:
    cleaned = value.strip().replace("Z", "+00:00")
    return datetime.fromisoformat(cleaned).astimezone(timezone.utc)


def _start_works(client: H2SUtsClient, dt: datetime) -> bool:
    try:
        client.fetch_registrations(start=_iso(dt))
        return True
    except H2SUtsError:
        return False


def find_earliest_safe_start(client: H2SUtsClient, lo: datetime, hi: datetime) -> datetime:
    """Binary search the boundary between a failing and a succeeding ``start``."""
    if _start_works(client, lo):
        return lo
    if not _start_works(client, hi):
        raise SystemExit(
            f"Even start={_iso(hi)} fails. The bad record is later than the search window; "
            f"re-run with --search-hi set past it."
        )
    while (hi - lo) > timedelta(seconds=1):
        mid = lo + (hi - lo) / 2
        if _start_works(client, mid):
            hi = mid
        else:
            lo = mid
        print(f"  probing... bad<={_iso(lo)}  good>={_iso(hi)}")
    return hi


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefix", default="cohort_3_")
    ap.add_argument("--start", help="Known-good ISO start; skips probing.")
    ap.add_argument("--search-lo", default=None, help="ISO lower bound for probing (default: current watermark).")
    ap.add_argument("--search-hi", default=None, help="ISO upper bound for probing (default: now).")
    ap.add_argument("--apply", action="store_true", help="Write the new watermark and gap record.")
    args = ap.parse_args()

    app = create_app()
    with app.app_context():
        current = get_sync_value(args.prefix, SYNC_KEY_REGISTRATION_START)
        print(f"current watermark: {current or '(none)'}")

        client = H2SUtsClient()

        if args.start:
            safe = _parse_iso(args.start)
            print(f"using supplied start: {_iso(safe)}")
            if not _start_works(client, safe):
                raise SystemExit(f"start={_iso(safe)} still returns an error; pick a later time.")
        else:
            lo = _parse_iso(args.search_lo) if args.search_lo else (
                _parse_iso(current) if current else datetime.now(timezone.utc) - timedelta(days=365)
            )
            hi = _parse_iso(args.search_hi) if args.search_hi else datetime.now(timezone.utc)
            print(f"probing for earliest safe start between {_iso(lo)} and {_iso(hi)}...")
            safe = find_earliest_safe_start(client, lo, hi)

        print(f"\nearliest safe start: {_iso(safe)}")
        print(f"unfetchable window : {current or '(beginning)'} -> {_iso(safe)}")

        if not args.apply:
            print("\nDry run. Re-run with --apply to write.")
            return

        add_registration_gap(
            args.prefix,
            gap_from=current or "(beginning)",
            gap_to=_iso(safe),
            reason=(
                "UTS registrations endpoint returns HTTP 500 for any window containing this "
                "range (upstream $convert to ObjectId fails on a non-ObjectId value). "
                "Run a full sync to backfill once Hack2Skill fixes the record."
            ),
        )
        set_sync_value(args.prefix, SYNC_KEY_REGISTRATION_START, _iso(safe))
        print(f"\n[OK] watermark set to {_iso(safe)}")
        for gap in get_registration_gaps(args.prefix):
            print(f"[GAP] {gap['from']} -> {gap['to']}")


if __name__ == "__main__":
    main()
