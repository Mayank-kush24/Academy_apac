"""
Create the project_submission table and set up its audit trigger.
Run once from project root: python init_project_submission.py
"""
import sys
import os

project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from sqlalchemy import text
from server.app import create_app
from server.models import db, ProjectSubmission


def init_project_submission():
    app = create_app()

    with app.app_context():
        inspector = db.inspect(db.engine)
        tables = inspector.get_table_names()

        if 'project_submission' in tables:
            print("OK: 'project_submission' table already exists")
        else:
            print("Creating 'project_submission' table...")
            ProjectSubmission.__table__.create(db.engine)
            print("OK: 'project_submission' table created")

        try:
            with db.engine.connect() as conn:
                conn.execute(text("""
                    DROP TRIGGER IF EXISTS tr_project_submission_log ON project_submission;
                    CREATE TRIGGER tr_project_submission_log
                        AFTER INSERT OR UPDATE OR DELETE ON project_submission
                        FOR EACH ROW EXECUTE PROCEDURE log_activity();
                """))
                conn.commit()
            print("OK: project_submission audit trigger created")
        except Exception as ex:
            print("WARN: Could not create audit trigger (ensure schema.sql has been run):", str(ex))

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
                        ELSIF p_table_name = 'project_submission' THEN RETURN COALESCE((p_row).id::TEXT, '');
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
            print("OK: get_record_identifier updated for project_submission")
        except Exception as ex:
            print("WARN: Could not update get_record_identifier:", str(ex))

        print("\nDone! project_submission table is ready.")


if __name__ == '__main__':
    init_project_submission()
