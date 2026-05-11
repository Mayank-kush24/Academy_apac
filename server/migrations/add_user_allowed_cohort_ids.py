"""
Add users.allowed_cohort_ids for per-user cohort visibility (RBAC).

Run from project root:
    python server/migrations/add_user_allowed_cohort_ids.py

Uses DATABASE_URL or server config.
"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from sqlalchemy import create_engine, text  # noqa: E402


def main():
    from server.config import Config

    url = os.environ.get("DATABASE_URL") or Config.SQLALCHEMY_DATABASE_URI
    if not url:
        print("Set DATABASE_URL or SQLALCHEMY_DATABASE_URI in Config.")
        sys.exit(1)

    engine = create_engine(url)
    ddl = """
    ALTER TABLE public.users
    ADD COLUMN IF NOT EXISTS allowed_cohort_ids JSONB NULL;
    COMMENT ON COLUMN public.users.allowed_cohort_ids IS
      'JSON array of cohort ids user may access; NULL = all enabled cohorts.';
    """
    with engine.connect() as conn:
        conn.execute(text(ddl))
        conn.commit()
    print("[OK] public.users.allowed_cohort_ids ensured")


if __name__ == "__main__":
    main()
