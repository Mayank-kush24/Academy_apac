"""
Database diagnostic script
Checks database connection, tables, and data
"""
import sys
import os

# Add project root to path
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from server.app import create_app
from server.models import db, User, UserPII

def check_database():
    """Check database status"""
    app = create_app()
    
    with app.app_context():
        print("=" * 60)
        print("DATABASE DIAGNOSTIC REPORT")
        print("=" * 60)
        
        # 1. Check database connection
        print("\n1. Checking database connection...")
        try:
            db.engine.connect()
            print("[OK] Database connection successful")
        except Exception as e:
            print(f"[ERROR] Database connection failed: {str(e)}")
            print("\nPlease check:")
            print("  - PostgreSQL is running")
            print("  - DATABASE_URL in .env file is correct")
            print("  - Database 'academy_apac' exists")
            return
        
        # 2. Check if tables exist
        print("\n2. Checking database tables...")
        try:
            inspector = db.inspect(db.engine)
            tables = inspector.get_table_names()
            
            required_tables = ['users', 'user_pii']
            for table in required_tables:
                if table in tables:
                    print(f"  [OK] Table '{table}' exists")
                else:
                    print(f"  [ERROR] Table '{table}' NOT found")
                    print(f"    Run: python init_database.py")
        except Exception as e:
            print(f"[ERROR] Error checking tables: {str(e)}")
            return
        
        # 3. Check data counts
        print("\n3. Checking data in tables...")
        try:
            user_count = User.query.count()
            print(f"  Users table: {user_count} records")
            
            user_pii_count = UserPII.query.count()
            print(f"  UserPII table: {user_pii_count} records")
            
            if user_pii_count == 0:
                print("\n  [WARNING] No data in UserPII table!")
                print("  To add data:")
                print("    1. Go to /import page")
                print("    2. Upload an Excel file with user data")
                print("    3. Or use the API endpoint: POST /api/import/upload")
        except Exception as e:
            print(f"[ERROR] Error checking data: {str(e)}")
            return
        
        # 4. Check sample data
        print("\n4. Sample data check...")
        try:
            sample_user_pii = UserPII.query.first()
            if sample_user_pii:
                print(f"  [OK] Found sample record:")
                print(f"    - ID: {sample_user_pii.id}")
                print(f"    - Email: {sample_user_pii.email or 'N/A'}")
                print(f"    - Name: {sample_user_pii.full_name or 'N/A'}")
                print(f"    - City: {sample_user_pii.city or 'N/A'}")
                print(f"    - Domain: {sample_user_pii.domain or 'N/A'}")
            else:
                print("  [WARNING] No sample records found")
        except Exception as e:
            print(f"[ERROR] Error checking sample data: {str(e)}")
        
        # 5. Summary
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        
        if user_pii_count == 0:
            print("\n[WARNING] ISSUE: No data in database")
            print("\nTo fix:")
            print("  1. Ensure tables are created: python init_database.py")
            print("  2. Import data via /import page or API")
            print("  3. Refresh the dashboard")
        else:
            print(f"\n[OK] Database has {user_pii_count} records")
            print("  If dashboard still shows no data:")
            print("  1. Check browser console for API errors")
            print("  2. Verify you're logged in (check localStorage for 'token')")
            print("  3. Check Flask server is running on port 3002")
            print("  4. Verify API endpoints are accessible")

if __name__ == '__main__':
    check_database()
