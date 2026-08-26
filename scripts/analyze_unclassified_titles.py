"""Report what the Unclassified bucket actually contains and what could resolve it.

Read-only. Groups unclassified designations by volume and checks how many would be
covered by the 700-title reference versus the existing index.
"""
import os
import sys
from collections import Counter

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import pandas as pd  # noqa: E402
from sqlalchemy import text  # noqa: E402

from server.app import create_app  # noqa: E402
from server.models import db  # noqa: E402
from server.utils.title_map import _clean_text, is_excluded_title, map_title  # noqa: E402

CSV = os.path.join(_ROOT, "700 Job titles _ C3 _ Gen ai apac - 700 New Job Titles.csv")
OCC = """(
    LOWER(occupation) LIKE '%professional%'
    OR LOWER(occupation) LIKE '%startup%'
    OR LOWER(occupation) LIKE '%freelance%'
)"""


def main():
    prefix = os.environ.get("ANALYZE_PREFIX", "cohort_3_")
    table = f"{prefix}{os.environ.get('ANALYZE_TABLE', 'user_pii_combined')}"

    app = create_app()
    with app.app_context():
        total = db.session.execute(
            text(f"SELECT COUNT(*) FROM {table} WHERE {OCC}")
        ).scalar()
        unclassified = db.session.execute(
            text(
                f"""SELECT COALESCE(NULLIF(TRIM(designation), ''), '(blank)') AS d, COUNT(*) n
                    FROM {table}
                    WHERE {OCC}
                      AND (broad_category IS NULL OR TRIM(broad_category) = '')
                    GROUP BY d ORDER BY n DESC"""
            )
        ).fetchall()

    n_unclassified = sum(int(n) for _, n in unclassified)
    print(f"{table}: {total} professional/startup/freelance rows")
    print(f"unclassified: {n_unclassified} rows across {len(unclassified)} distinct designations\n")

    print("top 25 unclassified designations:")
    for d, n in unclassified[:25]:
        print(f"  {n:6d}  {d[:70]}")

    # Why is each one unclassified today?
    reasons = Counter()
    excluded_rows = 0
    for d, n in unclassified:
        if d == "(blank)" or not _clean_text(d):
            reasons["blank"] += n
        elif is_excluded_title(d):
            reasons["excluded (student/degree/junk)"] += n
            excluded_rows += n
        else:
            sub, _ = map_title(d)
            reasons["real title, no index match" if sub == "Unclassified" else "would map now"] += n
    print("\nwhy unclassified:")
    for k, v in reasons.most_common():
        print(f"  {v:6d}  {k}")

    # How much would the 700-title reference add?
    ref = pd.read_csv(CSV)
    ref_norm = {_clean_text(t) for t in ref["title"] if _clean_text(t)}
    exact_hits = sum(
        n for d, n in unclassified if _clean_text(d) in ref_norm
    )
    print(f"\n700-title reference: {len(ref_norm)} normalized titles")
    print(f"exact matches against unclassified designations: {exact_hits} rows")


if __name__ == "__main__":
    main()
