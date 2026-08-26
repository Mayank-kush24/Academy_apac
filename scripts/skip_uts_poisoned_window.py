"""
Advance the UTS registration watermark past a record the upstream API cannot serve.

The Hack2Skill registrations endpoint aggregates with a $convert to ObjectId; when a
record holds a non-ObjectId value in that field the whole cursor dies with HTTP 500,
so every window containing it is unfetchable. There is no end-of-range parameter, so
the only way forward is to start after the bad record and record the skipped window
as a gap.

Sync Now now skips these windows automatically. This script remains for operators
who want to probe or advance the watermark without importing.

Usage:
  python scripts/skip_uts_poisoned_window.py                  # probe, show plan, no writes
  python scripts/skip_uts_poisoned_window.py --apply
  python scripts/skip_uts_poisoned_window.py --apply --start 2026-08-14T07:29:01Z
"""
import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from server.app import create_app
from server.utils.h2s_uts_client import H2SUtsClient, H2SUtsError
from server.utils.h2s_uts_sync import (
    POISON_GAP_REASON,
    SYNC_KEY_REGISTRATION_START,
    add_registration_gap,
    find_earliest_safe_registration_start,
    get_registration_gaps,
    get_sync_value,
    parse_uts_iso,
    registration_start_works,
    set_sync_value,
    uts_iso,
)


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
            safe = parse_uts_iso(args.start)
            print(f"using supplied start: {uts_iso(safe)}")
            if not registration_start_works(client, safe):
                raise SystemExit(f"start={uts_iso(safe)} still returns an error; pick a later time.")
        else:
            lo = parse_uts_iso(args.search_lo) if args.search_lo else (
                parse_uts_iso(current) if current else datetime.now(timezone.utc) - timedelta(days=365)
            )
            hi = parse_uts_iso(args.search_hi) if args.search_hi else datetime.now(timezone.utc)
            print(f"probing for earliest safe start between {uts_iso(lo)} and {uts_iso(hi)}...")
            try:
                safe = find_earliest_safe_registration_start(
                    client,
                    lo,
                    hi,
                    on_probe=lambda bad, good: print(
                        f"  probing... bad<={uts_iso(bad)}  good>={uts_iso(good)}"
                    ),
                )
            except H2SUtsError as exc:
                raise SystemExit(str(exc)) from exc

        print(f"\nearliest safe start: {uts_iso(safe)}")
        print(f"unfetchable window : {current or '(beginning)'} -> {uts_iso(safe)}")

        if not args.apply:
            print("\nDry run. Re-run with --apply to write.")
            return

        add_registration_gap(
            args.prefix,
            gap_from=current or "(beginning)",
            gap_to=uts_iso(safe),
            reason=POISON_GAP_REASON.format(bad=""),
        )
        set_sync_value(args.prefix, SYNC_KEY_REGISTRATION_START, uts_iso(safe))
        print(f"\n[OK] watermark set to {uts_iso(safe)}")
        for gap in get_registration_gaps(args.prefix):
            print(f"[GAP] {gap['from']} -> {gap['to']}")


if __name__ == "__main__":
    main()
