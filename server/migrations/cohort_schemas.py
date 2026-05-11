"""
Create PostgreSQL schemas cohort_2, cohort_3 with cloned participant tables (LIKE public.*).
Run once:  python server/migrations/cohort_schemas.py
Or from project root with PYTHONPATH set.
"""
import os
import sys

from sqlalchemy import text

# project root on path
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from server.app import create_app  # noqa: E402
from server.models import db  # noqa: E402

ALLOWED_SCHEMAS = ("cohort_2", "cohort_3")

_TABLES_LIKE = (
    "user_pii",
    "user_pii_injected",
    "bob_companies",
    "credit_links",
    "skillboost_profile",
    "skilllab_submission",
    "codelab_submission",
    "project_submission",
    "optional_mcq_verification",
    "optional_mcq_response",
    "main_mcq_response",
)


def _fk_statements(schema: str) -> list:
    s = schema
    return [
        f"""
        ALTER TABLE "{s}".skillboost_profile
        DROP CONSTRAINT IF EXISTS skillboost_profile_credit_link_id_fkey;
        ALTER TABLE "{s}".skillboost_profile
        ADD CONSTRAINT skillboost_profile_credit_link_id_fkey
        FOREIGN KEY (credit_link_id) REFERENCES "{s}".credit_links(id);
        """,
        f"""
        ALTER TABLE "{s}".skilllab_submission
        DROP CONSTRAINT IF EXISTS skilllab_submission_leader_email_fkey;
        ALTER TABLE "{s}".skilllab_submission
        ADD CONSTRAINT skilllab_submission_leader_email_fkey
        FOREIGN KEY (leader_email) REFERENCES "{s}".user_pii(email);
        """,
        f"""
        ALTER TABLE "{s}".codelab_submission
        DROP CONSTRAINT IF EXISTS codelab_submission_leader_email_fkey;
        ALTER TABLE "{s}".codelab_submission
        ADD CONSTRAINT codelab_submission_leader_email_fkey
        FOREIGN KEY (leader_email) REFERENCES "{s}".user_pii(email);
        """,
        f"""
        ALTER TABLE "{s}".project_submission
        DROP CONSTRAINT IF EXISTS project_submission_leader_email_fkey;
        ALTER TABLE "{s}".project_submission
        ADD CONSTRAINT project_submission_leader_email_fkey
        FOREIGN KEY (leader_email) REFERENCES "{s}".user_pii(email);
        """,
        f"""
        ALTER TABLE "{s}".optional_mcq_verification
        DROP CONSTRAINT IF EXISTS optional_mcq_verification_email_fkey;
        ALTER TABLE "{s}".optional_mcq_verification
        ADD CONSTRAINT optional_mcq_verification_email_fkey
        FOREIGN KEY (email) REFERENCES "{s}".user_pii(email);
        """,
        f"""
        ALTER TABLE "{s}".optional_mcq_response
        DROP CONSTRAINT IF EXISTS optional_mcq_response_email_fkey;
        ALTER TABLE "{s}".optional_mcq_response
        ADD CONSTRAINT optional_mcq_response_email_fkey
        FOREIGN KEY (email) REFERENCES "{s}".user_pii(email);
        """,
        f"""
        ALTER TABLE "{s}".main_mcq_response
        DROP CONSTRAINT IF EXISTS main_mcq_response_email_fkey;
        ALTER TABLE "{s}".main_mcq_response
        ADD CONSTRAINT main_mcq_response_email_fkey
        FOREIGN KEY (email) REFERENCES "{s}".user_pii(email);
        """,
    ]


def _view_statement(schema: str) -> str:
    s = schema
    return f"""
    DROP VIEW IF EXISTS "{s}".user_pii_combined CASCADE;
    CREATE VIEW "{s}".user_pii_combined AS
    SELECT id, registered_at, organization_name, class_stream, domain, designation, name, email,
           mobile_number, country, state, city, date_of_birth, gender, occupation,
           github_url, linkedin_url, utm_medium, bob_match, industry, persona, created_at, updated_at,
           'user_pii'::text AS source
    FROM "{s}".user_pii
    UNION ALL
    SELECT id, registered_at, organization_name, class_stream, domain, designation, name, email,
           mobile_number, country, state, city, date_of_birth, gender, occupation,
           github_url, linkedin_url, utm_medium, bob_match, industry, persona, created_at, updated_at,
           'user_pii_injected'::text AS source
    FROM "{s}".user_pii_injected i
    WHERE NOT EXISTS (SELECT 1 FROM "{s}".user_pii u WHERE u.email = i.email);
    """


def apply_schema(engine, schema: str) -> None:
    if schema not in ALLOWED_SCHEMAS:
        raise ValueError(f"Invalid schema {schema!r}")
    with engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
        for tbl in _TABLES_LIKE:
            conn.execute(
                text(
                    f'CREATE TABLE IF NOT EXISTS "{schema}"."{tbl}" '
                    f'(LIKE public."{tbl}" INCLUDING ALL)'
                )
            )
        for stmt in _fk_statements(schema):
            conn.execute(text(stmt))
        conn.execute(text(_view_statement(schema)))
    print(f"[OK] Schema {schema} tables + view user_pii_combined")


def main():
    app = create_app()
    with app.app_context():
        for sch in ALLOWED_SCHEMAS:
            try:
                apply_schema(db.engine, sch)
            except Exception as e:
                print(f"[FAIL] {sch}: {e}")
                raise


if __name__ == "__main__":
    main()
