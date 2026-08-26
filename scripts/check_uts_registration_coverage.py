"""Dry-run the reachable-registration fetch against the live UTS API.

Fetches only (no DB writes) and reports how many registrations the sliding-window
fetch recovers versus a single capped call, plus any window it had to step over.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from server.utils.h2s_uts_client import H2SUtsClient, extract_records  # noqa: E402
from server.utils.h2s_uts_sync import fetch_reachable_registrations  # noqa: E402

TS = "Timestamp"


def run(c, hints, label):
    t0 = time.time()
    records, gaps = fetch_reachable_registrations(c, None, hints=hints)
    secs = time.time() - t0
    emails = {str(r.get("Email", "")).strip().lower() for r in records if r.get("Email")}
    ts = sorted(str(r.get(TS)) for r in records if r.get(TS))
    print(f"\n{label}: {len(records)} rows, {len(emails)} unique, {secs:.0f}s")
    print(f"  range {ts[0]} .. {ts[-1]}")
    for g in gaps:
        print(f"  gap: {g['from']} .. {g['to']}  (bad value {g['bad']!r})")
    return emails


def main():
    c = H2SUtsClient()

    old = extract_records(c.fetch_registrations())
    print(f"single capped call: {len(old)}")

    hints = {}
    first = run(c, hints, "cold (searches boundaries)")
    print(f"  discovered hints: {hints}")

    second = run(c, dict(hints), "warm (reuses cached boundaries)")
    print(f"\nwarm matches cold: {first == second}")


if __name__ == "__main__":
    main()
