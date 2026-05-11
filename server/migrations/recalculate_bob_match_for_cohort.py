"""
Recompute bob_match on user_pii and user_pii_injected from bob_companies (raw SQL).

Use after loading cohort_*_bob_companies directly in PostgreSQL, or to fix drift.

Run from project root:
    python server/migrations/recalculate_bob_match_for_cohort.py 2

Uses the same logic as POST /api/import/bob/recalculate-matches?cohort_id=...
"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from server.app import create_app  # noqa: E402
from server.cohort_config import get_table_prefix  # noqa: E402
from server.utils.bob_match import recalculate_bob_match_with_prefix  # noqa: E402


def main():
    if len(sys.argv) < 2:
        print("Usage: python server/migrations/recalculate_bob_match_for_cohort.py <cohort_id>")
        sys.exit(1)
    cid = int(sys.argv[1])
    app = create_app()
    with app.app_context():
        prefix = get_table_prefix(cid)
        n = recalculate_bob_match_with_prefix(prefix)
        print(f"Cohort {cid} (table prefix {prefix!r}): {n} participant row(s) had bob_match changed.")


if __name__ == "__main__":
    main()
