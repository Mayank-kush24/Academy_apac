"""
Create the Support user (Profiles-only, view-only, copy-paste protected).
Email: support@genai-academy.local
Password: support_apac_2026
"""
import sys
import os
import bcrypt

project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from server.app import create_app
from server.models import db, User

SUPPORT_EMAIL = 'support@genai-academy.local'
SUPPORT_PASSWORD = 'support_apac_2026'
SUPPORT_NAME = 'Support'
SUPPORT_ALLOWED_PAGES = ['home', 'profiles']


def create_support_user():
    app = create_app()
    with app.app_context():
        existing = User.query.filter_by(email=SUPPORT_EMAIL).first()
        if existing:
            print(f"Support user already exists: {SUPPORT_EMAIL}")
            print("  To reset password, delete the user from User Management and run this script again.")
            return
        password_hash = bcrypt.hashpw(SUPPORT_PASSWORD.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        user = User(
            name=SUPPORT_NAME,
            email=SUPPORT_EMAIL,
            password_hash=password_hash,
            role='support',
            status='active',
            allowed_pages=SUPPORT_ALLOWED_PAGES,
        )
        db.session.add(user)
        db.session.commit()
        print("Support user created successfully.")
        print(f"  Email: {SUPPORT_EMAIL}")
        print(f"  Password: {SUPPORT_PASSWORD}")
        print("  Access: Home + Profiles only (view-only; copy/paste disabled on Profiles).")


if __name__ == '__main__':
    create_support_user()
