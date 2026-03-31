"""
Database migration script to add indexes for performance optimization
Run this script to add indexes on frequently queried columns
"""
import sys
import os

# Add project root to path
# Script is at: project_root/server/migrations/add_indexes.py
# So we need to go up 2 levels to get to project_root
script_path = os.path.abspath(__file__)
migrations_dir = os.path.dirname(script_path)  # server/migrations
server_dir = os.path.dirname(migrations_dir)   # server
project_root = os.path.dirname(server_dir)    # project root

# Add project root to Python path
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Also add server directory to path for imports
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

# Now import after path is set
from server.app import create_app
from server.models import db
from sqlalchemy import text

def add_indexes():
    """Add database indexes for performance optimization"""
    app = create_app()
    
    with app.app_context():
        print("Adding database indexes for performance optimization...")
        
        indexes = [
            # Email index (unique constraint already exists, but explicit index helps)
            ("CREATE INDEX IF NOT EXISTS idx_user_pii_email ON user_pii(email)", "Email index"),
            
            # Organization name index (frequently filtered)
            ("CREATE INDEX IF NOT EXISTS idx_user_pii_organization ON user_pii(organization_name)", "Organization name index"),
            
            # Domain index (frequently filtered and grouped)
            ("CREATE INDEX IF NOT EXISTS idx_user_pii_domain ON user_pii(domain)", "Domain index"),
            
            # Location indexes (frequently filtered)
            ("CREATE INDEX IF NOT EXISTS idx_user_pii_country ON user_pii(country)", "Country index"),
            ("CREATE INDEX IF NOT EXISTS idx_user_pii_state ON user_pii(state)", "State index"),
            ("CREATE INDEX IF NOT EXISTS idx_user_pii_city ON user_pii(city)", "City index"),
            
            # Date indexes (for time-based queries and sorting)
            ("CREATE INDEX IF NOT EXISTS idx_user_pii_created_at ON user_pii(created_at)", "Created at index"),
            ("CREATE INDEX IF NOT EXISTS idx_user_pii_registered_at ON user_pii(registered_at)", "Registered at index"),
            
            # Gender index (for distribution queries)
            ("CREATE INDEX IF NOT EXISTS idx_user_pii_gender ON user_pii(gender)", "Gender index"),
            
            # Class stream index
            ("CREATE INDEX IF NOT EXISTS idx_user_pii_class_stream ON user_pii(class_stream)", "Class stream index"),
            
            # Designation index
            ("CREATE INDEX IF NOT EXISTS idx_user_pii_designation ON user_pii(designation)", "Designation index"),
            
            # Occupation index
            ("CREATE INDEX IF NOT EXISTS idx_user_pii_occupation ON user_pii(occupation)", "Occupation index"),
            
            # Composite indexes for common query patterns
            ("CREATE INDEX IF NOT EXISTS idx_user_pii_created_at_org ON user_pii(created_at, organization_name)", "Created at + Organization composite index"),
            ("CREATE INDEX IF NOT EXISTS idx_user_pii_registered_at_domain ON user_pii(registered_at, domain)", "Registered at + Domain composite index"),
            
            # Full-text search indexes (for PostgreSQL)
            # Using GIN index for better text search performance
            ("CREATE INDEX IF NOT EXISTS idx_user_pii_name_trgm ON user_pii USING gin(name gin_trgm_ops)", "Name trigram index (requires pg_trgm extension)"),
            ("CREATE INDEX IF NOT EXISTS idx_user_pii_email_trgm ON user_pii USING gin(email gin_trgm_ops)", "Email trigram index"),

            # ── user_pii_injected (mirrors user_pii indexes for the UNION ALL view) ──
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

            # ── Submission / lab tables ──
            ("CREATE INDEX IF NOT EXISTS idx_skillboost_email ON skillboost_profile(email)", "skillboost_profile email"),
            ("CREATE INDEX IF NOT EXISTS idx_skilllab_leader_email ON skilllab_submission(leader_email)", "skilllab_submission leader_email"),
            ("CREATE INDEX IF NOT EXISTS idx_codelab_leader_email ON codelab_submission(leader_email)", "codelab_submission leader_email"),
            ("CREATE INDEX IF NOT EXISTS idx_project_submission_leader_email ON project_submission(leader_email)", "project_submission leader_email"),
            ("CREATE INDEX IF NOT EXISTS idx_mcq_email ON optional_mcq_response(email)", "optional_mcq_response email"),
            ("CREATE INDEX IF NOT EXISTS idx_mcq_track ON optional_mcq_response(track_number)", "optional_mcq_response track_number"),
            ("CREATE INDEX IF NOT EXISTS idx_main_mcq_email ON main_mcq_response(email)", "main_mcq_response email"),
            ("CREATE INDEX IF NOT EXISTS idx_main_mcq_track ON main_mcq_response(track_number)", "main_mcq_response track_number"),
        ]
        
        successful = 0
        failed = 0
        
        for index_sql, description in indexes:
            try:
                # Skip trigram indexes if extension not available
                if 'trgm' in index_sql:
                    try:
                        # Check if pg_trgm extension exists
                        result = db.session.execute(text("SELECT * FROM pg_extension WHERE extname = 'pg_trgm'"))
                        if not result.fetchone():
                            print(f"[SKIP] {description} - pg_trgm extension not installed")
                            print("  To enable: Run 'CREATE EXTENSION IF NOT EXISTS pg_trgm;' in PostgreSQL")
                            continue
                    except:
                        print(f"[SKIP] {description} - Could not check pg_trgm extension")
                        continue
                
                db.session.execute(text(index_sql))
                db.session.commit()
                print(f"[OK] {description}")
                successful += 1
            except Exception as e:
                db.session.rollback()
                print(f"[FAILED] {description}: {str(e)}")
                failed += 1
        
        print(f"\n[COMPLETE] Index creation complete: {successful} successful, {failed} failed")
        
        if failed == 0:
            print("\nAll indexes created successfully!")
        else:
            print("\n[WARNING] Some indexes failed to create. Check the errors above.")

if __name__ == '__main__':
    add_indexes()
