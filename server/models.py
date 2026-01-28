"""
Database models for Gen AI Academy APAC Edition
"""
from datetime import datetime
from uuid import uuid4
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.postgresql import UUID

# SQLAlchemy instance - engine options will be applied via app config
db = SQLAlchemy()


class UserPII(db.Model):
    """Table for storing user PII (Personally Identifiable Information)"""
    __tablename__ = 'user_pii'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    registered_at = db.Column(db.DateTime, nullable=True)
    organization_name = db.Column(db.String(255), nullable=True)
    class_stream = db.Column(db.String(255), nullable=True)
    domain = db.Column(db.String(255), nullable=True)
    designation = db.Column(db.String(255), nullable=True)
    name = db.Column(db.String(255), nullable=True)
    email = db.Column(db.String(255), unique=True, nullable=False, primary_key=False)
    mobile_number = db.Column(db.String(50), nullable=True)
    country = db.Column(db.String(100), nullable=True)
    state = db.Column(db.String(100), nullable=True)
    city = db.Column(db.String(100), nullable=True)
    date_of_birth = db.Column(db.Date, nullable=True)
    gender = db.Column(db.String(50), nullable=True)
    occupation = db.Column(db.String(255), nullable=True)
    github_url = db.Column(db.String(500), nullable=True)
    linkedin_url = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def to_dict(self):
        """Convert model to dictionary"""
        return {
            'id': str(self.id),
            'registered_at': self.registered_at.isoformat() if self.registered_at else None,
            'organization_name': self.organization_name,
            'class_stream': self.class_stream,
            'domain': self.domain,
            'designation': self.designation,
            'name': self.name,
            'email': self.email,
            'mobile_number': self.mobile_number,
            'country': self.country,
            'state': self.state,
            'city': self.city,
            'date_of_birth': self.date_of_birth.isoformat() if self.date_of_birth else None,
            'gender': self.gender,
            'occupation': self.occupation,
            'github_url': self.github_url,
            'linkedin_url': self.linkedin_url,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class User(db.Model):
    """Table for storing application users (admin, editor, viewer)"""
    __tablename__ = 'users'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(50), nullable=False, default='viewer')  # admin, editor, viewer
    status = db.Column(db.String(50), nullable=False, default='active')  # active, inactive
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        """Convert model to dictionary (exclude password)"""
        return {
            'id': str(self.id),
            'name': self.name,
            'email': self.email,
            'role': self.role,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
