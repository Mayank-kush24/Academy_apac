"""
Database initialization script
Creates all tables in the database
"""
import sys
import os

# Add project root to path
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from sqlalchemy import text
from server.app import create_app
from server.models import db, User, UserPII, ActivityLog, BobCompany, SkillboostProfile, CreditLink

def init_database():
    """Initialize database and create all tables"""
    app = create_app()
    
    with app.app_context():
        print("Creating database tables...")
        try:
            # Drop optional_mcq_response so it can be recreated with current schema (fixes column mismatches)
            try:
                with db.engine.connect() as conn:
                    conn.execute(text("DROP TRIGGER IF EXISTS tr_optional_mcq_response_log ON optional_mcq_response"))
                    conn.commit()
                print("OK: Dropped trigger on optional_mcq_response (if any)")
            except Exception as ex:
                print("WARN: Could not drop optional_mcq_response trigger (table may not exist):", str(ex))
            try:
                with db.engine.connect() as conn:
                    conn.execute(text("DROP TABLE IF EXISTS optional_mcq_response CASCADE"))
                    conn.commit()
                print("OK: Dropped optional_mcq_response table (will recreate with current schema)")
            except Exception as ex:
                print("WARN: Could not drop optional_mcq_response:", str(ex))

            # Create all tables
            db.create_all()
            print("OK: Database tables created successfully!")
            
            # Verify tables exist
            print("\nVerifying tables...")
            inspector = db.inspect(db.engine)
            tables = inspector.get_table_names()
            
            if 'users' in tables:
                print("OK: 'users' table exists")
            else:
                print("FAIL: 'users' table NOT found")
            
            if 'user_pii' in tables:
                print("OK: 'user_pii' table exists")
            else:
                print("FAIL: 'user_pii' table NOT found")
            
            if 'activity_logs' in tables:
                print("OK: 'activity_logs' table exists")
            else:
                print("FAIL: 'activity_logs' table NOT found")
            
            if 'bob_companies' in tables:
                print("OK: 'bob_companies' table exists")
            else:
                print("FAIL: 'bob_companies' table NOT found")
            
            if 'skillboost_profile' in tables:
                print("OK: 'skillboost_profile' table exists")
                # Drop FK to user_pii so we can import all Skill Lab emails (not only those in user_pii)
                try:
                    with db.engine.connect() as conn:
                        conn.execute(text("ALTER TABLE skillboost_profile DROP CONSTRAINT IF EXISTS fk_skillboost_profile_email"))
                        conn.commit()
                    print("OK: skillboost_profile: FK to user_pii removed (import all emails)")
                except Exception as ex:
                    print("WARN: Could not drop skillboost_profile FK (may already be dropped):", str(ex))
                # Ensure master_logs and skillboost_profile trigger exist (profile verification logs)
                try:
                    schema_path = os.path.join(project_root, 'schema.sql')
                    if os.path.isfile(schema_path):
                        with open(schema_path, 'r', encoding='utf-8') as f:
                            schema_sql = f.read()
                        with db.engine.connect() as conn:
                            conn.execute(text(schema_sql))
                            conn.commit()
                        print("OK: master_logs + skillboost_profile trigger applied (profile verification logs)")
                    else:
                        _apply_skillboost_master_logs(db)
                except Exception as ex:
                    try:
                        _apply_skillboost_master_logs(db)
                    except Exception as ex2:
                        print("WARN: Could not apply master_logs for skillboost_profile (run schema.sql manually):", str(ex2))
                # Add credit_link_id and email_sent_at to skillboost_profile (credit allocation + Sendy tracking)
                try:
                    with db.engine.connect() as conn:
                        conn.execute(text("ALTER TABLE skillboost_profile ADD COLUMN IF NOT EXISTS credit_link_id INTEGER REFERENCES credit_links(id)"))
                        conn.commit()
                    print("OK: skillboost_profile.credit_link_id column verified")
                except Exception as ex:
                    print("WARN: Could not add skillboost_profile.credit_link_id (create credit_links first or already exists):", str(ex))
                try:
                    with db.engine.connect() as conn:
                        conn.execute(text("ALTER TABLE skillboost_profile ADD COLUMN IF NOT EXISTS email_sent_at TIMESTAMP"))
                        conn.commit()
                    print("OK: skillboost_profile.email_sent_at column verified")
                except Exception as ex:
                    print("WARN: Could not add skillboost_profile.email_sent_at (may already exist):", str(ex))
            else:
                print("FAIL: 'skillboost_profile' table NOT found")

            if 'credit_links' in tables:
                print("OK: 'credit_links' table exists")
            else:
                print("FAIL: 'credit_links' table NOT found")

            if 'optional_mcq_verification' in tables:
                print("OK: 'optional_mcq_verification' table exists")
                try:
                    with db.engine.connect() as conn:
                        conn.execute(text("""
                            DROP TRIGGER IF EXISTS tr_optional_mcq_verification_log ON optional_mcq_verification;
                            CREATE TRIGGER tr_optional_mcq_verification_log
                                AFTER INSERT OR UPDATE OR DELETE ON optional_mcq_verification
                                FOR EACH ROW EXECUTE PROCEDURE log_activity()
                        """))
                        conn.commit()
                    print("OK: optional_mcq_verification audit trigger created")
                except Exception as ex:
                    print("WARN: optional_mcq_verification trigger (run schema.sql for master_logs):", str(ex))
            else:
                print("FAIL: 'optional_mcq_verification' table NOT found")

            if 'optional_mcq_response' in tables:
                print("OK: 'optional_mcq_response' table exists")
                # Create audit trigger (requires log_activity and get_record_identifier from schema.sql)
                try:
                    with db.engine.connect() as conn:
                        conn.execute(text("""
                            DROP TRIGGER IF EXISTS tr_optional_mcq_response_log ON optional_mcq_response;
                            CREATE TRIGGER tr_optional_mcq_response_log
                                AFTER INSERT OR UPDATE OR DELETE ON optional_mcq_response
                                FOR EACH ROW EXECUTE PROCEDURE log_activity()
                        """))
                        conn.commit()
                    print("OK: optional_mcq_response audit trigger created")
                except Exception as ex:
                    print("WARN: optional_mcq_response trigger (run schema.sql for master_logs):", str(ex))
            else:
                print("FAIL: 'optional_mcq_response' table NOT found")
            
            # Add allowed_pages column to users if missing (dynamic page access)
            try:
                with db.engine.connect() as conn:
                    conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS allowed_pages JSONB"))
                    conn.commit()
                print("OK: users.allowed_pages column verified")
            except Exception as ex:
                print("WARN: Could not add users.allowed_pages (may already exist):", str(ex))
            
            # Add bob_match column to user_pii if missing (Book of Business match)
            try:
                with db.engine.connect() as conn:
                    conn.execute(text("ALTER TABLE user_pii ADD COLUMN IF NOT EXISTS bob_match BOOLEAN NOT NULL DEFAULT FALSE"))
                    conn.commit()
                print("OK: user_pii.bob_match column verified")
            except Exception as ex:
                print("WARN: Could not add user_pii.bob_match (may already exist):", str(ex))
            
            # Add utm_medium column to user_pii if missing
            try:
                with db.engine.connect() as conn:
                    conn.execute(text("ALTER TABLE user_pii ADD COLUMN IF NOT EXISTS utm_medium VARCHAR(255)"))
                    conn.commit()
                print("OK: user_pii.utm_medium column verified")
            except Exception as ex:
                print("WARN: Could not add user_pii.utm_medium (may already exist):", str(ex))

            # Indexes for dashboard/analytics (faster filters and aggregations)
            try:
                with db.engine.connect() as conn:
                    for idx_name, idx_sql in [
                        ('idx_user_pii_registered_at', 'CREATE INDEX IF NOT EXISTS idx_user_pii_registered_at ON user_pii(registered_at)'),
                        ('idx_user_pii_created_at', 'CREATE INDEX IF NOT EXISTS idx_user_pii_created_at ON user_pii(created_at)'),
                        ('idx_user_pii_country', 'CREATE INDEX IF NOT EXISTS idx_user_pii_country ON user_pii(country)'),
                        ('idx_user_pii_bob_match', 'CREATE INDEX IF NOT EXISTS idx_user_pii_bob_match ON user_pii(bob_match)'),
                    ]:
                        conn.execute(text(idx_sql))
                        conn.commit()
                print("OK: user_pii indexes verified")
            except Exception as ex:
                print("WARN: Could not create user_pii indexes (may already exist):", str(ex))
            
            # Check if admin user exists
            admin_count = User.query.filter_by(role='admin').count()
            if admin_count == 0:
                print("\nWARN: No admin users found. Run 'python setup_admin.py' to create one.")
            else:
                print(f"\nOK: Found {admin_count} admin user(s)")
            
            print("\nDatabase initialization complete!")
            
        except Exception as e:
            print(f"\nFAIL: Error creating tables: {str(e)}")
            print("\nPlease check:")
            print("1. PostgreSQL is running")
            print("2. DATABASE_URL in .env file is correct")
            print("3. Database exists and user has proper permissions")
            sys.exit(1)

def _apply_skillboost_master_logs(db):
    """Apply master_logs table, get_record_identifier, log_activity, and skillboost_profile trigger."""
    with db.engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS master_logs (
                log_id           SERIAL PRIMARY KEY,
                table_name       VARCHAR(128) NOT NULL,
                operation_type   VARCHAR(16) NOT NULL CHECK (operation_type IN ('INSERT', 'UPDATE', 'DELETE')),
                record_identifier TEXT NOT NULL,
                old_values       JSONB,
                new_values       JSONB,
                changed_by       VARCHAR(255),
                "timestamp"      TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc'),
                additional_info  JSONB
            );
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_master_logs_table_name ON master_logs (table_name);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_master_logs_timestamp ON master_logs (\"timestamp\");"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_master_logs_changed_by ON master_logs (changed_by);"))
        conn.commit()
    with db.engine.connect() as conn:
        conn.execute(text("""
            CREATE OR REPLACE FUNCTION get_record_identifier(p_table_name TEXT, p_row RECORD)
            RETURNS TEXT AS $$
            BEGIN
                IF p_table_name = 'user_pii' THEN RETURN COALESCE((p_row).id::TEXT, '');
                ELSIF p_table_name = 'users' THEN RETURN COALESCE((p_row).id::TEXT, '');
                ELSIF p_table_name = 'skillboost_profile' THEN
                    RETURN COALESCE((p_row).email, '') || '|' || COALESCE((p_row).google_cloud_skills_boost_profile_link, '');
                ELSIF p_table_name = 'optional_mcq_verification' THEN RETURN COALESCE((p_row).id::TEXT, '');
                ELSIF p_table_name = 'optional_mcq_response' THEN RETURN COALESCE((p_row).id::TEXT, '');
                ELSE RETURN COALESCE((p_row).id::TEXT, '');
                END IF;
            EXCEPTION WHEN OTHERS THEN RETURN 'unknown';
            END;
            $$ LANGUAGE plpgsql;
        """))
        conn.commit()
    with db.engine.connect() as conn:
        conn.execute(text("""
            CREATE OR REPLACE FUNCTION log_activity()
            RETURNS TRIGGER AS $$
            DECLARE v_table_name VARCHAR(128); v_operation VARCHAR(16); v_record_id TEXT;
                    v_old JSONB; v_new JSONB; v_changed_by VARCHAR(255); v_additional JSONB;
            BEGIN
                v_table_name := TG_TABLE_NAME; v_operation := TG_OP;
                IF TG_OP = 'DELETE' THEN v_record_id := get_record_identifier(TG_TABLE_NAME, OLD); v_old := to_jsonb(OLD); v_new := NULL;
                ELSIF TG_OP = 'UPDATE' THEN v_record_id := get_record_identifier(TG_TABLE_NAME, NEW); v_old := to_jsonb(OLD); v_new := to_jsonb(NEW);
                ELSE v_record_id := get_record_identifier(TG_TABLE_NAME, NEW); v_old := NULL; v_new := to_jsonb(NEW);
                END IF;
                BEGIN v_changed_by := NULLIF(TRIM(current_setting('app.current_user', true)), ''); EXCEPTION WHEN OTHERS THEN v_changed_by := 'system'; END;
                IF v_changed_by IS NULL THEN v_changed_by := 'system'; END IF;
                BEGIN v_additional := NULLIF(TRIM(current_setting('app.current_user_extra', true)), '')::jsonb; EXCEPTION WHEN OTHERS THEN v_additional := NULL; END;
                INSERT INTO master_logs (table_name, operation_type, record_identifier, old_values, new_values, changed_by, "timestamp", additional_info)
                VALUES (v_table_name, v_operation, v_record_id, v_old, v_new, v_changed_by, NOW() AT TIME ZONE 'utc', v_additional);
                RETURN COALESCE(NEW, OLD);
            END;
            $$ LANGUAGE plpgsql;
        """))
        conn.commit()
    with db.engine.connect() as conn:
        conn.execute(text("""
            DROP TRIGGER IF EXISTS tr_skillboost_profile_log ON skillboost_profile;
            CREATE TRIGGER tr_skillboost_profile_log
                AFTER INSERT OR UPDATE OR DELETE ON skillboost_profile
                FOR EACH ROW EXECUTE PROCEDURE log_activity();
        """))
        conn.commit()


if __name__ == '__main__':
    init_database()
