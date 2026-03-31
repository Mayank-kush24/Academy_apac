"""
Create the codelab_submission table and set up its audit trigger.
Run once: python init_codelab_submission.py
"""
import sys
import os

project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from sqlalchemy import text
from server.app import create_app
from server.models import db, CodeLabSubmission


def init_codelab_submission():
    app = create_app()

    with app.app_context():
        inspector = db.inspect(db.engine)
        tables = inspector.get_table_names()

        if 'codelab_submission' in tables:
            print("OK: 'codelab_submission' table already exists")
            # Ensure track_number column exists (added after initial creation)
            try:
                with db.engine.connect() as conn:
                    conn.execute(text(
                        "ALTER TABLE codelab_submission "
                        "ADD COLUMN IF NOT EXISTS track_number INTEGER"
                    ))
                    conn.commit()
                print("OK: codelab_submission.track_number column verified")
            except Exception as ex:
                print("WARN: Could not add track_number column:", str(ex))
            # Ensure unique constraint exists
            try:
                with db.engine.connect() as conn:
                    conn.execute(text("""
                        DO $$
                        BEGIN
                            IF NOT EXISTS (
                                SELECT 1 FROM pg_constraint WHERE conname = 'uq_codelab_email_track_lab'
                            ) THEN
                                ALTER TABLE codelab_submission
                                ADD CONSTRAINT uq_codelab_email_track_lab
                                UNIQUE (leader_email, track_number, problem_statement);
                            END IF;
                        END $$;
                    """))
                    conn.commit()
                print("OK: unique constraint (leader_email, track_number, problem_statement) verified")
            except Exception as ex:
                print("WARN: Could not add unique constraint:", str(ex))
        else:
            print("Creating 'codelab_submission' table...")
            CodeLabSubmission.__table__.create(db.engine)
            print("OK: 'codelab_submission' table created")

        # Create audit trigger (requires log_activity from schema.sql / init_database)
        try:
            with db.engine.connect() as conn:
                conn.execute(text("""
                    DROP TRIGGER IF EXISTS tr_codelab_submission_log ON codelab_submission;
                    CREATE TRIGGER tr_codelab_submission_log
                        AFTER INSERT OR UPDATE OR DELETE ON codelab_submission
                        FOR EACH ROW EXECUTE PROCEDURE log_activity();
                """))
                conn.commit()
            print("OK: codelab_submission audit trigger created")
        except Exception as ex:
            print("WARN: Could not create audit trigger (ensure schema.sql has been run):", str(ex))

        # Update get_record_identifier to handle codelab_submission
        try:
            with db.engine.connect() as conn:
                conn.execute(text("""
                    CREATE OR REPLACE FUNCTION get_record_identifier(p_table_name TEXT, p_row RECORD)
                    RETURNS TEXT AS $$
                    BEGIN
                        IF p_table_name = 'user_pii' THEN RETURN COALESCE((p_row).id::TEXT, '');
                        ELSIF p_table_name = 'users' THEN RETURN COALESCE((p_row).id::TEXT, '');
                        ELSIF p_table_name = 'skillboost_profile' THEN
                            RETURN COALESCE((p_row).email, '') || '|' || COALESCE((p_row).google_cloud_skills_boost_profile_link, '');
                        ELSIF p_table_name = 'skilllab_submission' THEN RETURN COALESCE((p_row).id::TEXT, '');
                        ELSIF p_table_name = 'codelab_submission' THEN RETURN COALESCE((p_row).id::TEXT, '');
                        ELSIF p_table_name = 'optional_mcq_verification' THEN RETURN COALESCE((p_row).id::TEXT, '');
                        ELSIF p_table_name = 'optional_mcq_response' THEN RETURN COALESCE((p_row).id::TEXT, '');
                        ELSIF p_table_name = 'main_mcq_response' THEN RETURN COALESCE((p_row).id::TEXT, '');
                        ELSE RETURN COALESCE((p_row).id::TEXT, '');
                        END IF;
                    EXCEPTION WHEN OTHERS THEN RETURN 'unknown';
                    END;
                    $$ LANGUAGE plpgsql;
                """))
                conn.commit()
            print("OK: get_record_identifier updated for codelab_submission")
        except Exception as ex:
            print("WARN: Could not update get_record_identifier:", str(ex))

        print("\nDone! codelab_submission table is ready.")


if __name__ == '__main__':
    init_codelab_submission()
