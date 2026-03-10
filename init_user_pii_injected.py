"""
Create the user_pii_injected table only.
Run this script to create user_pii_injected with the same structure as user_pii.
Does not run init_database.py or modify any other tables.
"""
import sys
import os

project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from server.app import create_app
from server.models import db, UserPIIInjected


def init_user_pii_injected():
    app = create_app()
    with app.app_context():
        print("Creating table user_pii_injected...")
        try:
            UserPIIInjected.__table__.create(db.engine, checkfirst=True)
            print("OK: user_pii_injected table created or already exists.")
            inspector = db.inspect(db.engine)
            if 'user_pii_injected' in inspector.get_table_names():
                print("OK: Verified 'user_pii_injected' exists.")
            else:
                print("FAIL: 'user_pii_injected' not found after create.")
                sys.exit(1)
        except Exception as e:
            print(f"FAIL: {e}")
            sys.exit(1)


if __name__ == '__main__':
    init_user_pii_injected()
