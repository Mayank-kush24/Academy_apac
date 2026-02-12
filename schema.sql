-- Master audit log table and triggers for PostgreSQL
-- Use session variables app.current_user and app.current_user_extra (optional JSON)
-- so the application sets who made the change before each request.

-- =============================================================================
-- MASTER_LOGS TABLE
-- =============================================================================
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

CREATE INDEX IF NOT EXISTS idx_master_logs_table_name ON master_logs (table_name);
CREATE INDEX IF NOT EXISTS idx_master_logs_timestamp ON master_logs ("timestamp");
CREATE INDEX IF NOT EXISTS idx_master_logs_changed_by ON master_logs (changed_by);

-- =============================================================================
-- LOG_ACTIVITY() TRIGGER FUNCTION
-- Reads session variables: app.current_user (changed_by), app.current_user_extra (additional_info)
-- =============================================================================
CREATE OR REPLACE FUNCTION log_activity()
RETURNS TRIGGER AS $$
DECLARE
    v_table_name     VARCHAR(128);
    v_operation      VARCHAR(16);
    v_record_id      TEXT;
    v_old            JSONB;
    v_new            JSONB;
    v_changed_by     VARCHAR(255);
    v_additional     JSONB;
BEGIN
    v_table_name := TG_TABLE_NAME;
    v_operation  := TG_OP;

    -- Record identifier: single PK or composite (table-specific)
    IF TG_OP = 'DELETE' THEN
        v_record_id := get_record_identifier(TG_TABLE_NAME, OLD);
        v_old := to_jsonb(OLD);
        v_new := NULL;
    ELSIF TG_OP = 'UPDATE' THEN
        v_record_id := get_record_identifier(TG_TABLE_NAME, NEW);
        v_old := to_jsonb(OLD);
        v_new := to_jsonb(NEW);
    ELSE
        v_record_id := get_record_identifier(TG_TABLE_NAME, NEW);
        v_old := NULL;
        v_new := to_jsonb(NEW);
    END IF;

    -- changed_by: from session variable, default 'system' if not set
    BEGIN
        v_changed_by := NULLIF(TRIM(current_setting('app.current_user', true)), '');
    EXCEPTION WHEN OTHERS THEN
        v_changed_by := 'system';
    END;
    IF v_changed_by IS NULL THEN
        v_changed_by := 'system';
    END IF;

    -- additional_info: optional session variable (JSON string)
    BEGIN
        v_additional := NULLIF(TRIM(current_setting('app.current_user_extra', true)), '')::jsonb;
    EXCEPTION WHEN OTHERS THEN
        v_additional := NULL;
    END;

    INSERT INTO master_logs (
        table_name,
        operation_type,
        record_identifier,
        old_values,
        new_values,
        changed_by,
        "timestamp",
        additional_info
    ) VALUES (
        v_table_name,
        v_operation,
        v_record_id,
        v_old,
        v_new,
        v_changed_by,
        NOW() AT TIME ZONE 'utc',
        v_additional
    );
    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- HELPER: Build record_identifier (single or composite key per table)
-- =============================================================================
CREATE OR REPLACE FUNCTION get_record_identifier(p_table_name TEXT, p_row RECORD)
RETURNS TEXT AS $$
BEGIN
    IF p_table_name = 'user_pii' THEN
        RETURN COALESCE((p_row).id::TEXT, '');
    ELSIF p_table_name = 'users' THEN
        RETURN COALESCE((p_row).id::TEXT, '');
    ELSIF p_table_name = 'form_response' THEN
        RETURN COALESCE((p_row).id::TEXT, '');
    ELSIF p_table_name = 'aws_team_building' THEN
        RETURN COALESCE((p_row).id::TEXT, '');
    ELSIF p_table_name = 'project_submission' THEN
        RETURN COALESCE((p_row).id::TEXT, '');
    ELSIF p_table_name = 'verification' THEN
        RETURN COALESCE((p_row).id::TEXT, '');
    ELSIF p_table_name = 'kiro_submission' THEN
        RETURN COALESCE((p_row).id::TEXT, '');
    ELSIF p_table_name = 'hands_on_lab_completion' THEN
        RETURN COALESCE((p_row).id::TEXT, '');
    ELSIF p_table_name = 'skillboost_profile' THEN
        RETURN COALESCE((p_row).email, '') || '|' || COALESCE((p_row).google_cloud_skills_boost_profile_link, '');
    ELSIF p_table_name = 'skilllab_submission' THEN
        RETURN COALESCE((p_row).id::TEXT, '');
    ELSE
        -- Default: try single column 'id'
        RETURN COALESCE((p_row).id::TEXT, '');
    END IF;
EXCEPTION WHEN OTHERS THEN
    RETURN 'unknown';
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- TRIGGERS ON AUDITED TABLES (create only if table exists)
-- =============================================================================

-- user_pii
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'user_pii') THEN
        DROP TRIGGER IF EXISTS tr_user_pii_log ON user_pii;
        CREATE TRIGGER tr_user_pii_log
            AFTER INSERT OR UPDATE OR DELETE ON user_pii
            FOR EACH ROW EXECUTE PROCEDURE log_activity();
    END IF;
END $$;

-- users
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'users') THEN
        DROP TRIGGER IF EXISTS tr_users_log ON users;
        CREATE TRIGGER tr_users_log
            AFTER INSERT OR UPDATE OR DELETE ON users
            FOR EACH ROW EXECUTE PROCEDURE log_activity();
    END IF;
END $$;

-- skillboost_profile
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'skillboost_profile') THEN
        DROP TRIGGER IF EXISTS tr_skillboost_profile_log ON skillboost_profile;
        CREATE TRIGGER tr_skillboost_profile_log
            AFTER INSERT OR UPDATE OR DELETE ON skillboost_profile
            FOR EACH ROW EXECUTE PROCEDURE log_activity();
    END IF;
END $$;

-- skilllab_submission
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'skilllab_submission') THEN
        DROP TRIGGER IF EXISTS tr_skilllab_submission_log ON skilllab_submission;
        CREATE TRIGGER tr_skilllab_submission_log
            AFTER INSERT OR UPDATE OR DELETE ON skilllab_submission
            FOR EACH ROW EXECUTE PROCEDURE log_activity();
    END IF;
END $$;

-- =============================================================================
-- HOW TO ADD AUTO-LOGGING FOR A NEW TABLE
-- =============================================================================
-- 1. If the new table has a single-column PK named 'id', get_record_identifier
--    already falls back to (p_row).id::TEXT. For composite keys, add an
--    ELSIF branch in get_record_identifier() for your table_name returning
--    a stable string (e.g. (p_row).col1::TEXT || '|' || (p_row).col2::TEXT).
-- 2. Create the trigger (replace my_table with your table name):
--
--    DROP TRIGGER IF EXISTS tr_my_table_log ON my_table;
--    CREATE TRIGGER tr_my_table_log
--        AFTER INSERT OR UPDATE OR DELETE ON my_table
--        FOR EACH ROW EXECUTE PROCEDURE log_activity();
--
-- 3. Ensure all application writes to my_table go through code that sets
--    the session variable (Flask before_request sets app.current_user;
--    for background jobs set it to 'system' before the operation).
