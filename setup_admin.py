"""
Setup script to create initial admin user
"""
import sys
import os
import bcrypt
from dotenv import load_dotenv

# Add server directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'server'))

from server.app import create_app
from server.models import db, User

# Load environment variables
load_dotenv()


def create_admin_user():
    """Create an initial admin user"""
    app = create_app()
    
    with app.app_context():
        # Check if admin already exists
        existing_admin = User.query.filter_by(role='admin').first()
        if existing_admin:
            print(f"Admin user already exists: {existing_admin.email}")
            response = input("Do you want to create another admin? (y/n): ")
            if response.lower() != 'y':
                print("Exiting...")
                return
        
        # Get user input
        print("\n=== Create Admin User ===")
        name = input("Enter admin name: ").strip()
        email = input("Enter admin email: ").strip()
        password = input("Enter admin password: ").strip()
        
        if not name or not email or not password:
            print("Error: Name, email, and password are required")
            return
        
        # Check if email already exists
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            print(f"Error: User with email {email} already exists")
            return
        
        # Hash password
        password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        # Create admin user
        admin = User(
            name=name,
            email=email,
            password_hash=password_hash,
            role='admin',
            status='active'
        )
        
        try:
            db.session.add(admin)
            db.session.commit()
            print(f"\n✓ Admin user created successfully!")
            print(f"  Name: {name}")
            print(f"  Email: {email}")
            print(f"  Role: admin")
        except Exception as e:
            db.session.rollback()
            print(f"Error creating admin user: {str(e)}")


if __name__ == '__main__':
    create_admin_user()
