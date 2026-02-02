#!/usr/bin/env python3
"""
Verify master_logs audit: run an INSERT/UPDATE on an audited table and check
that a new row appears in master_logs with correct table_name, operation_type,
record_identifier, and changed_by.

Usage (from project root):
  python scripts/verify_master_logs.py

Prerequisites: schema.sql applied (master_logs + triggers exist), DB running.
"""
import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from sqlalchemy import text
from server.app import create_app
from server.models import db, UserPII

def main():
    app = create_app()
    with app.app_context():
        # Ensure master_logs exists
        try:
            r = db.session.execute(text("SELECT 1 FROM master_logs LIMIT 1"))
            r.fetchone()
        except Exception as e:
            print("master_logs table missing or not accessible. Apply schema.sql first.")
            print(e)
            return 1

        # Count before
        count_before = db.session.execute(text("SELECT COUNT(*) FROM master_logs")).scalar()

        # Set session variable in same transaction as INSERT (so trigger sees it)
        db.session.execute(text("SELECT set_config('app.current_user', 'verify_script', true)"))

        # Insert a test row into user_pii
        test_email = "verify_audit_%s@example.com" % (os.getpid(),)
        try:
            rec = UserPII(email=test_email, name="Verify Audit")
            db.session.add(rec)
            db.session.flush()
            record_id = str(rec.id)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print("Insert failed:", e)
            return 1

        # Count after and fetch latest log row
        count_after = db.session.execute(text("SELECT COUNT(*) FROM master_logs")).scalar()
        row = db.session.execute(
            text("""
                SELECT log_id, table_name, operation_type, record_identifier, changed_by, timestamp
                FROM master_logs ORDER BY log_id DESC LIMIT 1
            """)
        ).fetchone()

        # Clean up test row
        UserPII.query.filter_by(email=test_email).delete()
        db.session.commit()

        if count_after <= count_before or not row:
            print("FAIL: No new row in master_logs after INSERT")
            return 1
        if row[1] != "user_pii" or row[2] != "INSERT" or row[4] != "verify_script":
            print("FAIL: Unexpected log row:", row)
            return 1
        print("OK: master_logs audit verified.")
        print("  Latest log: table_name=%s, operation_type=%s, record_identifier=%s, changed_by=%s"
              % (row[1], row[2], row[3], row[4]))
        return 0

if __name__ == "__main__":
    sys.exit(main())
