"""
One-time migration: create credit_links table and add credit_link_id, email_sent_at to skillboost_profile.
Run from project root: python scripts/migrate_skilllab_credits.py
"""
import sys
import os

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from server.app import create_app
from server.models import db
from sqlalchemy import text


def migrate():
    app = create_app()
    with app.app_context():
        # 1. Create credit_links table if not exists
        with db.engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS credit_links (
                    id SERIAL PRIMARY KEY,
                    link_url VARCHAR(1024),
                    display_order INTEGER NOT NULL DEFAULT 0,
                    max_allocations INTEGER NOT NULL DEFAULT 2000,
                    created_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc')
                )
            """))
            conn.commit()
        print("OK credit_links table ready")

        # 2. Add credit_link_id to skillboost_profile if not exists
        with db.engine.connect() as conn:
            conn.execute(text("""
                ALTER TABLE skillboost_profile
                ADD COLUMN IF NOT EXISTS credit_link_id INTEGER REFERENCES credit_links(id)
            """))
            conn.commit()
        print("OK skillboost_profile.credit_link_id column ready")

        # 3. Add email_sent_at to skillboost_profile if not exists
        with db.engine.connect() as conn:
            conn.execute(text("""
                ALTER TABLE skillboost_profile
                ADD COLUMN IF NOT EXISTS email_sent_at TIMESTAMP
            """))
            conn.commit()
        print("OK skillboost_profile.email_sent_at column ready")
        print("\nMigration complete. Refresh the Skill Lab credits page.")


if __name__ == "__main__":
    try:
        migrate()
    except Exception as e:
        print("Migration failed:", e)
        sys.exit(1)
