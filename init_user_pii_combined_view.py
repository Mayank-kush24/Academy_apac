"""
Create or replace the user_pii_combined view.
Combines user_pii and user_pii_injected (user_pii wins on duplicate email).
Run this after both tables exist.
"""
import sys
import os

project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from sqlalchemy import text
from server.app import create_app
from server.models import db


def init_view():
    app = create_app()
    with app.app_context():
        inspector = db.inspect(db.engine)
        tables = inspector.get_table_names()

        if 'user_pii' not in tables:
            print("FAIL: user_pii table not found.")
            sys.exit(1)
        if 'user_pii_injected' not in tables:
            print("FAIL: user_pii_injected table not found. Run init_user_pii_injected.py first.")
            sys.exit(1)

        print("Creating user_pii_combined view...")
        try:
            with db.engine.connect() as conn:
                conn.execute(text("DROP VIEW IF EXISTS user_pii_combined CASCADE"))
                conn.execute(text("DROP TABLE IF EXISTS user_pii_combined CASCADE"))
                conn.commit()
            with db.engine.connect() as conn:
                conn.execute(text("""
                    CREATE VIEW user_pii_combined AS
                    SELECT id, registered_at, organization_name, class_stream, domain, designation, name, email,
                           mobile_number, country, state, city, date_of_birth, gender, occupation,
                           github_url, linkedin_url, utm_medium, bob_match, created_at, updated_at,
                           'user_pii' AS source
                    FROM user_pii
                    UNION ALL
                    SELECT id, registered_at, organization_name, class_stream, domain, designation, name, email,
                           mobile_number, country, state, city, date_of_birth, gender, occupation,
                           github_url, linkedin_url, utm_medium, bob_match, created_at, updated_at,
                           'user_pii_injected' AS source
                    FROM user_pii_injected i
                    WHERE NOT EXISTS (SELECT 1 FROM user_pii u WHERE u.email = i.email)
                """))
                conn.commit()
            print("OK: user_pii_combined view created or replaced.")
        except Exception as e:
            print(f"FAIL: {e}")
            sys.exit(1)


if __name__ == '__main__':
    init_view()
