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

from server.app import create_app
from server.models import db, User, UserPII, ActivityLog, BobCompany

def init_database():
    """Initialize database and create all tables"""
    app = create_app()
    
    with app.app_context():
        print("Creating database tables...")
        try:
            # Create all tables
            db.create_all()
            print("✓ Database tables created successfully!")
            
            # Verify tables exist
            print("\nVerifying tables...")
            inspector = db.inspect(db.engine)
            tables = inspector.get_table_names()
            
            if 'users' in tables:
                print("✓ 'users' table exists")
            else:
                print("✗ 'users' table NOT found")
            
            if 'user_pii' in tables:
                print("✓ 'user_pii' table exists")
            else:
                print("✗ 'user_pii' table NOT found")
            
            if 'activity_logs' in tables:
                print("✓ 'activity_logs' table exists")
            else:
                print("✗ 'activity_logs' table NOT found")
            
            if 'bob_companies' in tables:
                print("✓ 'bob_companies' table exists")
            else:
                print("✗ 'bob_companies' table NOT found")
            
            # Add allowed_pages column to users if missing (dynamic page access)
            try:
                from sqlalchemy import text
                with db.engine.connect() as conn:
                    conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS allowed_pages JSONB"))
                    conn.commit()
                print("✓ users.allowed_pages column verified")
            except Exception as ex:
                print("⚠ Could not add users.allowed_pages (may already exist):", ex)
            
            # Add bob_match column to user_pii if missing (Book of Business match)
            try:
                from sqlalchemy import text
                with db.engine.connect() as conn:
                    conn.execute(text("ALTER TABLE user_pii ADD COLUMN IF NOT EXISTS bob_match BOOLEAN NOT NULL DEFAULT FALSE"))
                    conn.commit()
                print("✓ user_pii.bob_match column verified")
            except Exception as ex:
                print("⚠ Could not add user_pii.bob_match (may already exist):", ex)
            
            # Add utm_medium column to user_pii if missing
            try:
                from sqlalchemy import text
                with db.engine.connect() as conn:
                    conn.execute(text("ALTER TABLE user_pii ADD COLUMN IF NOT EXISTS utm_medium VARCHAR(255)"))
                    conn.commit()
                print("✓ user_pii.utm_medium column verified")
            except Exception as ex:
                print("⚠ Could not add user_pii.utm_medium (may already exist):", ex)

            # Indexes for dashboard/analytics (faster filters and aggregations)
            try:
                from sqlalchemy import text
                with db.engine.connect() as conn:
                    for idx_name, idx_sql in [
                        ('idx_user_pii_registered_at', 'CREATE INDEX IF NOT EXISTS idx_user_pii_registered_at ON user_pii(registered_at)'),
                        ('idx_user_pii_created_at', 'CREATE INDEX IF NOT EXISTS idx_user_pii_created_at ON user_pii(created_at)'),
                        ('idx_user_pii_country', 'CREATE INDEX IF NOT EXISTS idx_user_pii_country ON user_pii(country)'),
                        ('idx_user_pii_bob_match', 'CREATE INDEX IF NOT EXISTS idx_user_pii_bob_match ON user_pii(bob_match)'),
                    ]:
                        conn.execute(text(idx_sql))
                        conn.commit()
                print("✓ user_pii indexes verified")
            except Exception as ex:
                print("⚠ Could not create user_pii indexes (may already exist):", ex)
            
            # Check if admin user exists
            admin_count = User.query.filter_by(role='admin').count()
            if admin_count == 0:
                print("\n⚠ No admin users found. Run 'python setup_admin.py' to create one.")
            else:
                print(f"\n✓ Found {admin_count} admin user(s)")
            
            print("\nDatabase initialization complete!")
            
        except Exception as e:
            print(f"\n✗ Error creating tables: {str(e)}")
            print("\nPlease check:")
            print("1. PostgreSQL is running")
            print("2. DATABASE_URL in .env file is correct")
            print("3. Database exists and user has proper permissions")
            sys.exit(1)

if __name__ == '__main__':
    init_database()
