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
from server.models import db, User, UserPII

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
