"""
Database migration script to add indexes for performance optimization.

Run from project root:
  python server/migrations/add_indexes.py

Does NOT start the full Flask app (avoids create_all, view rebuilds, and competing
with a running dev server for locks). Uses DATABASE_URL from .env only.

If the script appears stuck: stop the Flask server first, or another session may be
holding locks on the same tables. Large tables: CREATE INDEX can take many minutes;
progress is printed before each statement.
"""
import sys
import os

script_path = os.path.abspath(__file__)
migrations_dir = os.path.dirname(script_path)
server_dir = os.path.dirname(migrations_dir)
project_root = os.path.dirname(server_dir)

if project_root not in sys.path:
    sys.path.insert(0, project_root)
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

from dotenv import load_dotenv
from sqlalchemy import create_engine, text


def _indexes_list():
    return [
        ("CREATE INDEX IF NOT EXISTS idx_user_pii_email ON user_pii(email)", "Email index"),
        ("CREATE INDEX IF NOT EXISTS idx_user_pii_organization ON user_pii(organization_name)", "Organization name index"),
        ("CREATE INDEX IF NOT EXISTS idx_user_pii_domain ON user_pii(domain)", "Domain index"),
        ("CREATE INDEX IF NOT EXISTS idx_user_pii_country ON user_pii(country)", "Country index"),
        ("CREATE INDEX IF NOT EXISTS idx_user_pii_state ON user_pii(state)", "State index"),
        ("CREATE INDEX IF NOT EXISTS idx_user_pii_city ON user_pii(city)", "City index"),
        ("CREATE INDEX IF NOT EXISTS idx_user_pii_created_at ON user_pii(created_at)", "Created at index"),
        ("CREATE INDEX IF NOT EXISTS idx_user_pii_registered_at ON user_pii(registered_at)", "Registered at index"),
        ("CREATE INDEX IF NOT EXISTS idx_user_pii_gender ON user_pii(gender)", "Gender index"),
        ("CREATE INDEX IF NOT EXISTS idx_user_pii_class_stream ON user_pii(class_stream)", "Class stream index"),
        ("CREATE INDEX IF NOT EXISTS idx_user_pii_designation ON user_pii(designation)", "Designation index"),
        ("CREATE INDEX IF NOT EXISTS idx_user_pii_occupation ON user_pii(occupation)", "Occupation index"),
        ("CREATE INDEX IF NOT EXISTS idx_user_pii_created_at_org ON user_pii(created_at, organization_name)", "Created at + Organization composite index"),
        ("CREATE INDEX IF NOT EXISTS idx_user_pii_registered_at_domain ON user_pii(registered_at, domain)", "Registered at + Domain composite index"),
        ("CREATE INDEX IF NOT EXISTS idx_user_pii_name_trgm ON user_pii USING gin(name gin_trgm_ops)", "Name trigram index (requires pg_trgm extension)"),
        ("CREATE INDEX IF NOT EXISTS idx_user_pii_email_trgm ON user_pii USING gin(email gin_trgm_ops)", "Email trigram index"),
        ("CREATE INDEX IF NOT EXISTS idx_upi_email ON user_pii_injected(email)", "user_pii_injected email"),
        ("CREATE INDEX IF NOT EXISTS idx_upi_organization ON user_pii_injected(organization_name)", "user_pii_injected organization_name"),
        ("CREATE INDEX IF NOT EXISTS idx_upi_domain ON user_pii_injected(domain)", "user_pii_injected domain"),
        ("CREATE INDEX IF NOT EXISTS idx_upi_country ON user_pii_injected(country)", "user_pii_injected country"),
        ("CREATE INDEX IF NOT EXISTS idx_upi_state ON user_pii_injected(state)", "user_pii_injected state"),
        ("CREATE INDEX IF NOT EXISTS idx_upi_city ON user_pii_injected(city)", "user_pii_injected city"),
        ("CREATE INDEX IF NOT EXISTS idx_upi_created_at ON user_pii_injected(created_at)", "user_pii_injected created_at"),
        ("CREATE INDEX IF NOT EXISTS idx_upi_registered_at ON user_pii_injected(registered_at)", "user_pii_injected registered_at"),
        ("CREATE INDEX IF NOT EXISTS idx_upi_gender ON user_pii_injected(gender)", "user_pii_injected gender"),
        ("CREATE INDEX IF NOT EXISTS idx_upi_occupation ON user_pii_injected(occupation)", "user_pii_injected occupation"),
        ("CREATE INDEX IF NOT EXISTS idx_skillboost_email ON skillboost_profile(email)", "skillboost_profile email"),
        ("CREATE INDEX IF NOT EXISTS idx_skilllab_leader_email ON skilllab_submission(leader_email)", "skilllab_submission leader_email"),
        ("CREATE INDEX IF NOT EXISTS idx_codelab_leader_email ON codelab_submission(leader_email)", "codelab_submission leader_email"),
        ("CREATE INDEX IF NOT EXISTS idx_project_submission_leader_email ON project_submission(leader_email)", "project_submission leader_email"),
        ("CREATE INDEX IF NOT EXISTS idx_mcq_email ON optional_mcq_response(email)", "optional_mcq_response email"),
        ("CREATE INDEX IF NOT EXISTS idx_mcq_track ON optional_mcq_response(track_number)", "optional_mcq_response track_number"),
        ("CREATE INDEX IF NOT EXISTS idx_main_mcq_email ON main_mcq_response(email)", "main_mcq_response email"),
        ("CREATE INDEX IF NOT EXISTS idx_main_mcq_track ON main_mcq_response(track_number)", "main_mcq_response track_number"),
        ("CREATE INDEX IF NOT EXISTS idx_codelab_leader_track ON codelab_submission(leader_email, track_number)", "codelab_submission leader_email+track"),
        ("CREATE INDEX IF NOT EXISTS idx_optional_mcq_email_track ON optional_mcq_response(email, track_number)", "optional_mcq_response email+track"),
        ("CREATE INDEX IF NOT EXISTS idx_main_mcq_email_track ON main_mcq_response(email, track_number)", "main_mcq_response email+track"),
        ("CREATE INDEX IF NOT EXISTS idx_codelab_lower_leader ON codelab_submission (lower(leader_email))", "codelab lower(leader_email)"),
        ("CREATE INDEX IF NOT EXISTS idx_skilllab_lower_leader ON skilllab_submission (lower(leader_email))", "skilllab lower(leader_email)"),
        ("CREATE INDEX IF NOT EXISTS idx_project_lower_leader ON project_submission (lower(leader_email))", "project lower(leader_email)"),
        ("CREATE INDEX IF NOT EXISTS idx_optional_mcq_lower_email ON optional_mcq_response (lower(email))", "optional_mcq lower(email)"),
        ("CREATE INDEX IF NOT EXISTS idx_main_mcq_lower_email ON main_mcq_response (lower(email))", "main_mcq lower(email)"),
    ]


def _track_progress_only_indexes():
    """Subset for users who already ran the full script; avoids long runs on user_pii."""
    return [
        ("CREATE INDEX IF NOT EXISTS idx_codelab_leader_track ON codelab_submission(leader_email, track_number)", "codelab_submission leader_email+track"),
        ("CREATE INDEX IF NOT EXISTS idx_optional_mcq_email_track ON optional_mcq_response(email, track_number)", "optional_mcq_response email+track"),
        ("CREATE INDEX IF NOT EXISTS idx_main_mcq_email_track ON main_mcq_response(email, track_number)", "main_mcq_response email+track"),
        ("CREATE INDEX IF NOT EXISTS idx_codelab_lower_leader ON codelab_submission (lower(leader_email))", "codelab lower(leader_email)"),
        ("CREATE INDEX IF NOT EXISTS idx_skilllab_lower_leader ON skilllab_submission (lower(leader_email))", "skilllab lower(leader_email)"),
        ("CREATE INDEX IF NOT EXISTS idx_project_lower_leader ON project_submission (lower(leader_email))", "project lower(leader_email)"),
        ("CREATE INDEX IF NOT EXISTS idx_optional_mcq_lower_email ON optional_mcq_response (lower(email))", "optional_mcq lower(email)"),
        ("CREATE INDEX IF NOT EXISTS idx_main_mcq_lower_email ON main_mcq_response (lower(email))", "main_mcq lower(email)"),
    ]


def add_indexes(track_progress_only=False):
    load_dotenv()
    from server.config import Config

    url = Config.SQLALCHEMY_DATABASE_URI
    print("add_indexes: using direct SQLAlchemy engine (full Flask app is NOT loaded).", flush=True)
    print(f"add_indexes: connecting (timeout 30s)…", flush=True)

    connect_args = {}
    if url.startswith("postgresql"):
        connect_args["connect_timeout"] = 30

    engine = create_engine(
        url,
        pool_pre_ping=True,
        pool_size=1,
        max_overflow=0,
        connect_args=connect_args,
    )

    indexes = _track_progress_only_indexes() if track_progress_only else _indexes_list()
    n = len(indexes)

    successful = 0
    failed = 0
    skipped = 0

    with engine.connect() as conn:
        for i, (index_sql, description) in enumerate(indexes):
            print(f"[{i + 1}/{n}] {description} …", flush=True)
            if "trgm" in index_sql:
                try:
                    r = conn.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm'"))
                    if r.fetchone() is None:
                        print("      [SKIP] pg_trgm not installed — run: CREATE EXTENSION IF NOT EXISTS pg_trgm;", flush=True)
                        skipped += 1
                        continue
                except Exception as ex:
                    print(f"      [SKIP] could not check pg_trgm: {ex}", flush=True)
                    skipped += 1
                    continue

            try:
                conn.execute(text(index_sql))
                conn.commit()
                print("      [OK]", flush=True)
                successful += 1
            except Exception as e:
                conn.rollback()
                print(f"      [FAILED] {e}", flush=True)
                failed += 1

    engine.dispose()
    print(f"\n[COMPLETE] {successful} ok, {failed} failed, {skipped} skipped", flush=True)


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Create DB indexes (no Flask app startup).")
    p.add_argument(
        "--track-progress-only",
        action="store_true",
        help="Only create track-progress / submission-related indexes (faster if the rest already exist).",
    )
    args = p.parse_args()
    add_indexes(track_progress_only=args.track_progress_only)
