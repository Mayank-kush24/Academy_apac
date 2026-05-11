"""
Create Cohort 2 tables in the PUBLIC PostgreSQL schema using a cohort_2_ prefix.

All table names:
    cohort_2_user_pii
    cohort_2_user_pii_injected
    cohort_2_bob_companies
    cohort_2_credit_links
    cohort_2_skillboost_profile
    cohort_2_skilllab_submission
    cohort_2_codelab_submission
    cohort_2_project_submission
    cohort_2_optional_mcq_verification
    cohort_2_optional_mcq_response
    cohort_2_main_mcq_response

View:
    cohort_2_user_pii_combined  (UNION of cohort_2_user_pii + cohort_2_user_pii_injected)

Run from the project root:
    python server/migrations/create_cohort2_tables.py

Uses DATABASE_URL env variable, or falls back to server/config.py.
This script is idempotent — safe to re-run (uses IF NOT EXISTS everywhere).
"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from sqlalchemy import create_engine, text  # noqa: E402

PREFIX = "cohort_2_"

# ---------------------------------------------------------------------------
# Table DDL  (all in public schema, named with PREFIX)
# ---------------------------------------------------------------------------

_DDL_USER_PII = f"""
CREATE TABLE IF NOT EXISTS {PREFIX}user_pii (
    id                UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    registered_at     TIMESTAMP,
    organization_name VARCHAR(255),
    class_stream      VARCHAR(255),
    domain            VARCHAR(255),
    designation       VARCHAR(255),
    name              VARCHAR(255),
    email             VARCHAR(255)  NOT NULL UNIQUE,
    mobile_number     VARCHAR(50),
    country           VARCHAR(100),
    state             VARCHAR(100),
    city              VARCHAR(100),
    date_of_birth     DATE,
    gender            VARCHAR(50),
    occupation        VARCHAR(255),
    github_url        VARCHAR(500),
    linkedin_url      VARCHAR(500),
    utm_medium        VARCHAR(255),
    bob_match         BOOLEAN       NOT NULL DEFAULT FALSE,
    industry          VARCHAR(255),
    persona           VARCHAR(100),
    created_at        TIMESTAMP     NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMP     NOT NULL DEFAULT NOW()
);
"""

_DDL_USER_PII_INJECTED = f"""
CREATE TABLE IF NOT EXISTS {PREFIX}user_pii_injected (
    id                UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    registered_at     TIMESTAMP,
    organization_name VARCHAR(255),
    class_stream      VARCHAR(255),
    domain            VARCHAR(255),
    designation       VARCHAR(255),
    name              VARCHAR(255),
    email             VARCHAR(255)  NOT NULL UNIQUE,
    mobile_number     VARCHAR(50),
    country           VARCHAR(100),
    state             VARCHAR(100),
    city              VARCHAR(100),
    date_of_birth     DATE,
    gender            VARCHAR(50),
    occupation        VARCHAR(255),
    github_url        VARCHAR(500),
    linkedin_url      VARCHAR(500),
    utm_medium        VARCHAR(255),
    bob_match         BOOLEAN       NOT NULL DEFAULT FALSE,
    industry          VARCHAR(255),
    persona           VARCHAR(100),
    created_at        TIMESTAMP     NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMP     NOT NULL DEFAULT NOW()
);
"""

_DDL_BOB_COMPANIES = f"""
CREATE TABLE IF NOT EXISTS {PREFIX}bob_companies (
    id              SERIAL        PRIMARY KEY,
    company_name    VARCHAR(500)  NOT NULL,
    normalized_name VARCHAR(500)
);
CREATE INDEX IF NOT EXISTS ix_{PREFIX}bob_companies_normalized
    ON {PREFIX}bob_companies (normalized_name);
"""

_DDL_CREDIT_LINKS = f"""
CREATE TABLE IF NOT EXISTS {PREFIX}credit_links (
    id              SERIAL    PRIMARY KEY,
    link_url        VARCHAR(1024),
    display_order   INTEGER   NOT NULL DEFAULT 0,
    max_allocations INTEGER   NOT NULL DEFAULT 3000,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);
"""

_DDL_SKILLBOOST_PROFILE = f"""
CREATE TABLE IF NOT EXISTS {PREFIX}skillboost_profile (
    email                                   VARCHAR(255)  NOT NULL,
    google_cloud_skills_boost_profile_link  VARCHAR(1024) NOT NULL,
    valid           BOOLEAN      NOT NULL DEFAULT FALSE,
    remarks         VARCHAR(1024),
    credit_link_id  INTEGER,
    email_sent_at   TIMESTAMP,
    created_at      TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP    NOT NULL DEFAULT NOW(),
    PRIMARY KEY (email, google_cloud_skills_boost_profile_link)
);
"""

_DDL_SKILLLAB_SUBMISSION = f"""
CREATE TABLE IF NOT EXISTS {PREFIX}skilllab_submission (
    id                UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    team_name         VARCHAR(255),
    leader_name       VARCHAR(255),
    leader_email      VARCHAR(255) NOT NULL,
    leader_phone      VARCHAR(50),
    team_size         INTEGER,
    problem_statement TEXT,
    upload_screenshot VARCHAR(1024),
    created_at        TIMESTAMP    NOT NULL DEFAULT NOW(),
    created_by_name   VARCHAR(255),
    created_by_email  VARCHAR(255),
    updated_at        TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_by_name   VARCHAR(255),
    updated_by_email  VARCHAR(255),
    valid             BOOLEAN      NOT NULL DEFAULT FALSE,
    remark            TEXT,
    completion_date   TIMESTAMP,
    last_verified_at  TIMESTAMP
);
"""

_DDL_CODELAB_SUBMISSION = f"""
CREATE TABLE IF NOT EXISTS {PREFIX}codelab_submission (
    id                UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    track_number      INTEGER,
    team_name         VARCHAR(255),
    leader_name       VARCHAR(255),
    leader_email      VARCHAR(255) NOT NULL,
    leader_phone      VARCHAR(50),
    team_size         INTEGER,
    problem_statement TEXT,
    upload_screenshot VARCHAR(1024),
    created_at        TIMESTAMP    NOT NULL DEFAULT NOW(),
    created_by_name   VARCHAR(255),
    created_by_email  VARCHAR(255),
    updated_at        TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_by_name   VARCHAR(255),
    updated_by_email  VARCHAR(255),
    valid             BOOLEAN      NOT NULL DEFAULT FALSE,
    remark            TEXT,
    completion_date   TIMESTAMP,
    last_verified_at  TIMESTAMP,
    CONSTRAINT uq_{PREFIX}codelab_email_track_lab
        UNIQUE (leader_email, track_number, problem_statement)
);
"""

_DDL_PROJECT_SUBMISSION = f"""
CREATE TABLE IF NOT EXISTS {PREFIX}project_submission (
    id                        UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    track_number              INTEGER      NOT NULL,
    team_name                 VARCHAR(255),
    leader_name               VARCHAR(255),
    leader_email              VARCHAR(255) NOT NULL,
    leader_phone              VARCHAR(50),
    team_size                 INTEGER,
    problem_statement         TEXT,
    cloud_run_deployment_link VARCHAR(1024),
    github_repository_link    VARCHAR(1024),
    demo_video_link           VARCHAR(1024),
    final_project_ppt         VARCHAR(1024),
    created_at                TIMESTAMP    NOT NULL DEFAULT NOW(),
    created_by_name           VARCHAR(255),
    created_by_email          VARCHAR(255),
    updated_at                TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_by_name           VARCHAR(255),
    updated_by_email          VARCHAR(255),
    valid                     BOOLEAN      NOT NULL DEFAULT FALSE,
    remark                    TEXT,
    score                     NUMERIC(10, 2),
    CONSTRAINT uq_{PREFIX}project_email_track
        UNIQUE (leader_email, track_number)
);
"""

_DDL_OPTIONAL_MCQ_VERIFICATION = f"""
CREATE TABLE IF NOT EXISTS {PREFIX}optional_mcq_verification (
    id               UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    email            VARCHAR(255) NOT NULL,
    name             VARCHAR(255),
    created_at       TIMESTAMP    NOT NULL DEFAULT NOW(),
    created_by_name  VARCHAR(255),
    created_by_email VARCHAR(255),
    updated_at       TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_by_name  VARCHAR(255),
    updated_by_email VARCHAR(255),
    valid            BOOLEAN      NOT NULL DEFAULT FALSE,
    remark           TEXT
);
"""

_DDL_OPTIONAL_MCQ_RESPONSE = f"""
CREATE TABLE IF NOT EXISTS {PREFIX}optional_mcq_response (
    id               UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    track_number     INTEGER      NOT NULL,
    team_name        VARCHAR(512),
    leader_name      VARCHAR(255),
    email            VARCHAR(255) NOT NULL,
    leader_phone     VARCHAR(50),
    team_size        INTEGER,
    problem_statement TEXT,
    question_1       TEXT,
    question_2       TEXT,
    question_3       TEXT,
    question_4       TEXT,
    question_5       TEXT,
    question_6       TEXT,
    question_7       TEXT,
    question_8       TEXT,
    question_9       TEXT,
    question_10      TEXT,
    score            INTEGER,
    created_at       TIMESTAMP,
    created_by_name  VARCHAR(255),
    created_by_email VARCHAR(255),
    updated_at       TIMESTAMP,
    updated_by_name  VARCHAR(255),
    updated_by_email VARCHAR(255)
);
"""

_DDL_MAIN_MCQ_RESPONSE = f"""
CREATE TABLE IF NOT EXISTS {PREFIX}main_mcq_response (
    id               UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    track_number     INTEGER      NOT NULL,
    leader_name      VARCHAR(255),
    email            VARCHAR(255) NOT NULL,
    leader_phone     VARCHAR(50),
    team_size        INTEGER,
    problem_statement TEXT,
    question_1       TEXT,
    question_2       TEXT,
    question_3       TEXT,
    question_4       TEXT,
    question_5       TEXT,
    question_6       TEXT,
    question_7       TEXT,
    question_8       TEXT,
    question_9       TEXT,
    question_10      TEXT,
    score            INTEGER,
    created_at       TIMESTAMP,
    created_by_name  VARCHAR(255),
    created_by_email VARCHAR(255),
    updated_at       TIMESTAMP,
    updated_by_name  VARCHAR(255),
    updated_by_email VARCHAR(255),
    CONSTRAINT uq_{PREFIX}main_mcq_track_email
        UNIQUE (track_number, email)
);
"""

# ---------------------------------------------------------------------------
# Foreign keys (applied after all tables exist)
# ---------------------------------------------------------------------------

_FK_STATEMENTS = [
    # skillboost_profile → credit_links
    f"""
    ALTER TABLE {PREFIX}skillboost_profile
        DROP CONSTRAINT IF EXISTS fk_{PREFIX}skillboost_credit_link;
    ALTER TABLE {PREFIX}skillboost_profile
        ADD CONSTRAINT fk_{PREFIX}skillboost_credit_link
        FOREIGN KEY (credit_link_id) REFERENCES {PREFIX}credit_links(id);
    """,
    # skilllab_submission → user_pii
    f"""
    ALTER TABLE {PREFIX}skilllab_submission
        DROP CONSTRAINT IF EXISTS fk_{PREFIX}skilllab_leader_email;
    ALTER TABLE {PREFIX}skilllab_submission
        ADD CONSTRAINT fk_{PREFIX}skilllab_leader_email
        FOREIGN KEY (leader_email) REFERENCES {PREFIX}user_pii(email);
    """,
    # codelab_submission → user_pii
    f"""
    ALTER TABLE {PREFIX}codelab_submission
        DROP CONSTRAINT IF EXISTS fk_{PREFIX}codelab_leader_email;
    ALTER TABLE {PREFIX}codelab_submission
        ADD CONSTRAINT fk_{PREFIX}codelab_leader_email
        FOREIGN KEY (leader_email) REFERENCES {PREFIX}user_pii(email);
    """,
    # project_submission → user_pii
    f"""
    ALTER TABLE {PREFIX}project_submission
        DROP CONSTRAINT IF EXISTS fk_{PREFIX}project_leader_email;
    ALTER TABLE {PREFIX}project_submission
        ADD CONSTRAINT fk_{PREFIX}project_leader_email
        FOREIGN KEY (leader_email) REFERENCES {PREFIX}user_pii(email);
    """,
    # optional_mcq_verification → user_pii
    f"""
    ALTER TABLE {PREFIX}optional_mcq_verification
        DROP CONSTRAINT IF EXISTS fk_{PREFIX}opt_mcq_verif_email;
    ALTER TABLE {PREFIX}optional_mcq_verification
        ADD CONSTRAINT fk_{PREFIX}opt_mcq_verif_email
        FOREIGN KEY (email) REFERENCES {PREFIX}user_pii(email);
    """,
    # optional_mcq_response → user_pii
    f"""
    ALTER TABLE {PREFIX}optional_mcq_response
        DROP CONSTRAINT IF EXISTS fk_{PREFIX}opt_mcq_resp_email;
    ALTER TABLE {PREFIX}optional_mcq_response
        ADD CONSTRAINT fk_{PREFIX}opt_mcq_resp_email
        FOREIGN KEY (email) REFERENCES {PREFIX}user_pii(email);
    """,
    # main_mcq_response → user_pii
    f"""
    ALTER TABLE {PREFIX}main_mcq_response
        DROP CONSTRAINT IF EXISTS fk_{PREFIX}main_mcq_resp_email;
    ALTER TABLE {PREFIX}main_mcq_response
        ADD CONSTRAINT fk_{PREFIX}main_mcq_resp_email
        FOREIGN KEY (email) REFERENCES {PREFIX}user_pii(email);
    """,
]

# ---------------------------------------------------------------------------
# user_pii_combined view
# ---------------------------------------------------------------------------

_DDL_VIEW = f"""
DROP VIEW IF EXISTS {PREFIX}user_pii_combined CASCADE;
CREATE VIEW {PREFIX}user_pii_combined AS
SELECT id, registered_at, organization_name, class_stream, domain, designation,
       name, email, mobile_number, country, state, city, date_of_birth, gender,
       occupation, github_url, linkedin_url, utm_medium, bob_match, industry,
       persona, created_at, updated_at,
       'user_pii'::text AS source
FROM {PREFIX}user_pii
UNION ALL
SELECT id, registered_at, organization_name, class_stream, domain, designation,
       name, email, mobile_number, country, state, city, date_of_birth, gender,
       occupation, github_url, linkedin_url, utm_medium, bob_match, industry,
       persona, created_at, updated_at,
       'user_pii_injected'::text AS source
FROM {PREFIX}user_pii_injected i
WHERE NOT EXISTS (
    SELECT 1 FROM {PREFIX}user_pii u WHERE u.email = i.email
);
"""

# ---------------------------------------------------------------------------
# Ordered steps
# ---------------------------------------------------------------------------

_ALL_DDL = [
    (_DDL_USER_PII,                  f"{PREFIX}user_pii"),
    (_DDL_USER_PII_INJECTED,         f"{PREFIX}user_pii_injected"),
    (_DDL_BOB_COMPANIES,             f"{PREFIX}bob_companies"),
    (_DDL_CREDIT_LINKS,              f"{PREFIX}credit_links"),
    (_DDL_SKILLBOOST_PROFILE,        f"{PREFIX}skillboost_profile"),
    (_DDL_SKILLLAB_SUBMISSION,       f"{PREFIX}skilllab_submission"),
    (_DDL_CODELAB_SUBMISSION,        f"{PREFIX}codelab_submission"),
    (_DDL_PROJECT_SUBMISSION,        f"{PREFIX}project_submission"),
    (_DDL_OPTIONAL_MCQ_VERIFICATION, f"{PREFIX}optional_mcq_verification"),
    (_DDL_OPTIONAL_MCQ_RESPONSE,     f"{PREFIX}optional_mcq_response"),
    (_DDL_MAIN_MCQ_RESPONSE,         f"{PREFIX}main_mcq_response"),
]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_migration(database_url: str) -> None:
    engine = create_engine(database_url)
    with engine.begin() as conn:
        for ddl, label in _ALL_DDL:
            conn.execute(text(ddl))
            print(f"  [OK] Table  {label}")

        for stmt in _FK_STATEMENTS:
            conn.execute(text(stmt))
        print(f"  [OK] Foreign keys ({len(_FK_STATEMENTS)} constraints)")

        conn.execute(text(_DDL_VIEW))
        print(f"  [OK] View   {PREFIX}user_pii_combined")

    print(f"\n[DONE] All Cohort 2 tables created with prefix '{PREFIX}' in public schema.")
    print("\nTables in your database:")
    for _, label in _ALL_DDL:
        print(f"  • {label}")
    print(f"  • {PREFIX}user_pii_combined  (view)")


def _get_database_url() -> str:
    url = os.environ.get("DATABASE_URL") or os.environ.get("DB_URL")
    if url:
        return url
    try:
        from server.config import Config  # type: ignore
        cfg_url = getattr(Config, "SQLALCHEMY_DATABASE_URI", None)
        if cfg_url:
            return cfg_url
    except Exception:
        pass
    raise RuntimeError(
        "DATABASE_URL not found.\n"
        "Set the DATABASE_URL environment variable, e.g.:\n"
        "  $env:DATABASE_URL='postgresql://user:pass@localhost/dbname'\n"
        "  python server/migrations/create_cohort2_tables.py"
    )


def main() -> None:
    print(f"=== Creating Cohort 2 tables (prefix: '{PREFIX}') in public schema ===\n")
    db_url = _get_database_url()
    try:
        from urllib.parse import urlparse, urlunparse
        p = urlparse(db_url)
        masked = p._replace(
            netloc=f"{p.username}:***@{p.hostname}"
            + (f":{p.port}" if p.port else "")
        )
        print(f"Database: {urlunparse(masked)}\n")
    except Exception:
        pass
    run_migration(db_url)


if __name__ == "__main__":
    main()
