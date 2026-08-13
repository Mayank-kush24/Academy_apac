"""
Seed / refresh cohort_3_credit_links with five Skill Lab catalog URLs
(2000 max allocations each).

- Empty table: inserts all five links.
- Existing rows: updates link_url by display_order (keeps max_allocations).

Run from project root:
    python server/migrations/seed_cohort3_credit_links.py

Uses DATABASE_URL or server/config.py.
"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from sqlalchemy import create_engine, text  # noqa: E402

COHORT3_CREDIT_LINKS = [
    ("https://www.skills.google/catalog?qlcampaign=6m-GAAAE-45", 1, 2000),
    ("https://www.skills.google/catalog?qlcampaign=6m-GAAAE-46", 2, 2000),
    ("https://www.skills.google/catalog?qlcampaign=6m-GAAAE-47", 3, 2000),
    ("https://www.skills.google/catalog?qlcampaign=6m-GAAAE-48", 4, 2000),
    ("https://www.skills.google/catalog?qlcampaign=6m-GAAAE-49", 5, 2000),
]


def main():
    url = os.environ.get("DATABASE_URL")
    if not url:
        try:
            from server import config as _cfg  # noqa: WPS433

            url = getattr(_cfg, "DATABASE_URL", None) or getattr(_cfg, "SQLALCHEMY_DATABASE_URI", None)
        except Exception:
            url = None
    if not url:
        print("DATABASE_URL not set and config has no database URL.")
        sys.exit(1)

    engine = create_engine(url)
    with engine.begin() as conn:
        n = conn.execute(text("SELECT COUNT(*) FROM cohort_3_credit_links")).scalar()
        if n and int(n) > 0:
            for link_url, display_order, _max_allocations in COHORT3_CREDIT_LINKS:
                result = conn.execute(
                    text(
                        """
                        UPDATE cohort_3_credit_links
                        SET link_url = :link_url
                        WHERE display_order = :display_order
                        """
                    ),
                    {"link_url": link_url, "display_order": display_order},
                )
                if result.rowcount == 0:
                    conn.execute(
                        text(
                            """
                            INSERT INTO cohort_3_credit_links (link_url, display_order, max_allocations)
                            VALUES (:link_url, :display_order, :max_allocations)
                            """
                        ),
                        {
                            "link_url": link_url,
                            "display_order": display_order,
                            "max_allocations": 2000,
                        },
                    )
            print(f"Updated cohort_3_credit_links URLs ({n} existing row(s)).")
            return
        for link_url, display_order, max_allocations in COHORT3_CREDIT_LINKS:
            conn.execute(
                text(
                    """
                    INSERT INTO cohort_3_credit_links (link_url, display_order, max_allocations)
                    VALUES (:link_url, :display_order, :max_allocations)
                    """
                ),
                {
                    "link_url": link_url,
                    "display_order": display_order,
                    "max_allocations": max_allocations,
                },
            )
    print("Seeded cohort_3_credit_links: 5 links, 2000 max allocations each.")


if __name__ == "__main__":
    main()
