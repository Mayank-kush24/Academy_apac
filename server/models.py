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
    utm_medium = db.Column(db.String(255), nullable=True)
    bob_match = db.Column(db.Boolean, default=False, nullable=False)
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
            'utm_medium': self.utm_medium,
            'bob_match': bool(self.bob_match),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class BobCompany(db.Model):
    """Table for Book of Business company names (matched against UserPII.organization_name)."""
    __tablename__ = 'bob_companies'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    company_name = db.Column(db.String(500), nullable=False)
    normalized_name = db.Column(db.String(500), nullable=True, index=True)


class User(db.Model):
    """Table for storing application users (admin, editor, viewer)"""
    __tablename__ = 'users'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(50), nullable=False, default='viewer')  # admin, editor, viewer
    status = db.Column(db.String(50), nullable=False, default='active')  # active, inactive
    allowed_pages = db.Column(db.JSON, nullable=True)  # list of page ids user can see, e.g. ['home','dashboard','profiles']; null = use role defaults
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        """Convert model to dictionary (exclude password)"""
        return {
            'id': str(self.id),
            'name': self.name,
            'email': self.email,
            'role': self.role,
            'status': self.status,
            'allowed_pages': self.allowed_pages,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class CreditLink(db.Model):
    """
    Skill Lab credit links (up to 5). Each link can be allocated to max_allocations (e.g. 2000) users.
    """
    __tablename__ = 'credit_links'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    link_url = db.Column(db.String(1024), nullable=True)  # URL or identifier sent via Sendy
    display_order = db.Column(db.Integer, default=0, nullable=False)  # 1-5, order when allocating
    max_allocations = db.Column(db.Integer, default=2000, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'link_url': self.link_url,
            'display_order': self.display_order,
            'max_allocations': self.max_allocations,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class SkillboostProfile(db.Model):
    """
    Skill Lab / Google Skills Boost profile links per user (email).
    PK: (email, google_cloud_skills_boost_profile_link).
    Do not overwrite rows where valid = TRUE when importing.
    Email is not FK to user_pii so we can import all XLSX rows; profile page shows
    skillboost_profiles for a user by email when that user exists in user_pii.
    """
    __tablename__ = 'skillboost_profile'

    email = db.Column(db.String(255), nullable=False, primary_key=True)
    google_cloud_skills_boost_profile_link = db.Column(db.String(1024), nullable=False, primary_key=True)
    valid = db.Column(db.Boolean, default=False, nullable=False)  # verification result
    remarks = db.Column(db.String(1024), nullable=True)
    credit_link_id = db.Column(db.Integer, db.ForeignKey('credit_links.id'), nullable=True)  # which of 5 links allocated
    email_sent_at = db.Column(db.DateTime, nullable=True)  # when credit email was marked dispatched (Sendy)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            'email': self.email,
            'google_cloud_skills_boost_profile_link': self.google_cloud_skills_boost_profile_link,
            'valid': bool(self.valid),
            'remarks': self.remarks,
            'credit_link_id': self.credit_link_id,
            'email_sent_at': self.email_sent_at.isoformat() if self.email_sent_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class ActivityLog(db.Model):
    """Table for storing activity logs (create/update/delete on any tracked table)"""
    __tablename__ = 'activity_logs'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    action = db.Column(db.String(20), nullable=False)  # 'create', 'update', 'delete'
    entity_type = db.Column(db.String(64), nullable=False)  # 'user_pii', 'user', etc.
    entity_id = db.Column(db.String(64), nullable=False)  # primary key of the record (as string)
    actor_user_id = db.Column(UUID(as_uuid=True), nullable=True)  # app user who performed action (if any)
    changes = db.Column(db.JSON, nullable=True)  # list of { "field", "old_value", "new_value" } for updates
    snapshot_before = db.Column(db.JSON, nullable=True)  # full record state before (for update/delete)
    snapshot_after = db.Column(db.JSON, nullable=True)  # full record state after (for create/update)
    summary = db.Column(db.String(500), nullable=True)  # human-readable one-liner

    def to_dict(self):
        return {
            'id': str(self.id),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'action': self.action,
            'entity_type': self.entity_type,
            'entity_id': self.entity_id,
            'actor_user_id': str(self.actor_user_id) if self.actor_user_id else None,
            'changes': self.changes,
            'snapshot_before': self.snapshot_before,
            'snapshot_after': self.snapshot_after,
            'summary': self.summary,
        }
