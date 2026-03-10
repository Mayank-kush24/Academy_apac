"""
Database models for Gen AI Academy APAC Edition
"""
from datetime import datetime
from uuid import uuid4
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import MetaData, Table, Column
from sqlalchemy.dialects.postgresql import UUID

# SQLAlchemy instance - engine options will be applied via app config
db = SQLAlchemy()

# Separate metadata for read-only view (so db.create_all() does not create a table)
_view_metadata = MetaData()


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


class UserPIIInjected(db.Model):
    """Table for storing injected user PII (same structure as user_pii)."""
    __tablename__ = 'user_pii_injected'

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


# View created by init_database (raw SQL). Table definition uses separate metadata so create_all() skips it.
_user_pii_combined_table = Table(
    'user_pii_combined',
    _view_metadata,
    Column('id', UUID(as_uuid=True), primary_key=True),
    Column('registered_at', db.DateTime, nullable=True),
    Column('organization_name', db.String(255), nullable=True),
    Column('class_stream', db.String(255), nullable=True),
    Column('domain', db.String(255), nullable=True),
    Column('designation', db.String(255), nullable=True),
    Column('name', db.String(255), nullable=True),
    Column('email', db.String(255), nullable=False),
    Column('mobile_number', db.String(50), nullable=True),
    Column('country', db.String(100), nullable=True),
    Column('state', db.String(100), nullable=True),
    Column('city', db.String(100), nullable=True),
    Column('date_of_birth', db.Date, nullable=True),
    Column('gender', db.String(50), nullable=True),
    Column('occupation', db.String(255), nullable=True),
    Column('github_url', db.String(500), nullable=True),
    Column('linkedin_url', db.String(500), nullable=True),
    Column('utm_medium', db.String(255), nullable=True),
    Column('bob_match', db.Boolean, default=False, nullable=False),
    Column('created_at', db.DateTime, nullable=False),
    Column('updated_at', db.DateTime, nullable=False),
    Column('source', db.String(32), nullable=True),
)


class UserPIICombined(db.Model):
    """
    Read-only view: user_pii UNION user_pii_injected (emails not in user_pii).
    One row per email; user_pii wins on duplicate. Created by init_database (raw SQL view).
    """
    __table__ = _user_pii_combined_table

    def to_dict(self):
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
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'source': self.source,
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
    Skill Lab credit links (up to 5). Each link can be allocated to max_allocations (e.g. 3000) users.
    """
    __tablename__ = 'credit_links'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    link_url = db.Column(db.String(1024), nullable=True)  # URL or identifier sent via Sendy
    display_order = db.Column(db.Integer, default=0, nullable=False)  # 1-5, order when allocating
    max_allocations = db.Column(db.Integer, default=3000, nullable=False)
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


class SkillLabSubmission(db.Model):
    """
    Skill Lab submission verification table.
    Each row represents a team submission that an intern verifies manually.
    leader_email is FK to user_pii.email.
    """
    __tablename__ = 'skilllab_submission'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    team_name = db.Column(db.String(255), nullable=True)
    leader_name = db.Column(db.String(255), nullable=True)
    leader_email = db.Column(db.String(255), db.ForeignKey('user_pii.email'), nullable=False)
    leader_phone = db.Column(db.String(50), nullable=True)
    team_size = db.Column(db.Integer, nullable=True)
    problem_statement = db.Column(db.Text, nullable=True)
    upload_screenshot = db.Column(db.String(1024), nullable=True)  # URL/path to screenshot
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    created_by_name = db.Column(db.String(255), nullable=True)
    created_by_email = db.Column(db.String(255), nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    updated_by_name = db.Column(db.String(255), nullable=True)
    updated_by_email = db.Column(db.String(255), nullable=True)
    valid = db.Column(db.Boolean, default=False, nullable=False)
    remark = db.Column(db.Text, nullable=True)

    # Relationship to UserPII
    leader = db.relationship('UserPII', foreign_keys=[leader_email], primaryjoin='SkillLabSubmission.leader_email == UserPII.email', lazy='joined')

    def to_dict(self):
        return {
            'id': str(self.id),
            'team_name': self.team_name,
            'leader_name': self.leader_name,
            'leader_email': self.leader_email,
            'leader_phone': self.leader_phone,
            'team_size': self.team_size,
            'problem_statement': self.problem_statement,
            'upload_screenshot': self.upload_screenshot,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'created_by_name': self.created_by_name,
            'created_by_email': self.created_by_email,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'updated_by_name': self.updated_by_name,
            'updated_by_email': self.updated_by_email,
            'valid': bool(self.valid),
            'remark': self.remark,
        }


class CodeLabSubmission(db.Model):
    """
    Code Lab submission verification table.
    Each row = one participant (email) in a specific track + lab.
    track_number: 1, 2, or 3.  problem_statement: e.g. "Lab 1", "Lab 2".
    Unique on (leader_email, track_number, problem_statement).
    """
    __tablename__ = 'codelab_submission'
    __table_args__ = (
        db.UniqueConstraint('leader_email', 'track_number', 'problem_statement', name='uq_codelab_email_track_lab'),
    )

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    track_number = db.Column(db.Integer, nullable=True)
    team_name = db.Column(db.String(255), nullable=True)
    leader_name = db.Column(db.String(255), nullable=True)
    leader_email = db.Column(db.String(255), db.ForeignKey('user_pii.email'), nullable=False)
    leader_phone = db.Column(db.String(50), nullable=True)
    team_size = db.Column(db.Integer, nullable=True)
    problem_statement = db.Column(db.Text, nullable=True)
    upload_screenshot = db.Column(db.String(1024), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    created_by_name = db.Column(db.String(255), nullable=True)
    created_by_email = db.Column(db.String(255), nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    updated_by_name = db.Column(db.String(255), nullable=True)
    updated_by_email = db.Column(db.String(255), nullable=True)
    valid = db.Column(db.Boolean, default=False, nullable=False)
    remark = db.Column(db.Text, nullable=True)

    leader = db.relationship('UserPII', foreign_keys=[leader_email], primaryjoin='CodeLabSubmission.leader_email == UserPII.email', lazy='joined')

    def to_dict(self):
        return {
            'id': str(self.id),
            'track_number': self.track_number,
            'team_name': self.team_name,
            'leader_name': self.leader_name,
            'leader_email': self.leader_email,
            'leader_phone': self.leader_phone,
            'team_size': self.team_size,
            'problem_statement': self.problem_statement,
            'upload_screenshot': self.upload_screenshot,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'created_by_name': self.created_by_name,
            'created_by_email': self.created_by_email,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'updated_by_name': self.updated_by_name,
            'updated_by_email': self.updated_by_email,
            'valid': bool(self.valid),
            'remark': self.remark,
        }


class OptionalMcqVerification(db.Model):
    """
    Optional MCQ verification table.
    One row per participant (email FK to user_pii). Interns verify manually: valid flag and remark.
    """
    __tablename__ = 'optional_mcq_verification'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    email = db.Column(db.String(255), db.ForeignKey('user_pii.email'), nullable=False)
    name = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    created_by_name = db.Column(db.String(255), nullable=True)
    created_by_email = db.Column(db.String(255), nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    updated_by_name = db.Column(db.String(255), nullable=True)
    updated_by_email = db.Column(db.String(255), nullable=True)
    valid = db.Column(db.Boolean, default=False, nullable=False)
    remark = db.Column(db.Text, nullable=True)

    participant = db.relationship('UserPII', foreign_keys=[email], primaryjoin='OptionalMcqVerification.email == UserPII.email', lazy='joined')

    def to_dict(self):
        return {
            'id': str(self.id),
            'email': self.email,
            'name': self.name,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'created_by_name': self.created_by_name,
            'created_by_email': self.created_by_email,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'updated_by_name': self.updated_by_name,
            'updated_by_email': self.updated_by_email,
            'valid': bool(self.valid),
            'remark': self.remark,
        }


class OptionalMcqResponse(db.Model):
    """
    Optional MCQ response table. One row per (track_number, email).
    Columns match XLSX: Leader Name, Leader Email (FK to user_pii), Leader Phone, Team size,
    Problem Statements, Q1.–Q10., plus created/updated audit fields. Team Name is skipped.
    """
    __tablename__ = 'optional_mcq_response'
    __table_args__ = (db.UniqueConstraint('track_number', 'email', name='uq_optional_mcq_response_track_email'),)

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    track_number = db.Column(db.Integer, nullable=False)  # 1, 2, or 3
    leader_name = db.Column(db.String(255), nullable=True)
    email = db.Column(db.String(255), db.ForeignKey('user_pii.email'), nullable=False)  # Leader Email
    leader_phone = db.Column(db.String(50), nullable=True)
    team_size = db.Column(db.Integer, nullable=True)
    problem_statement = db.Column(db.Text, nullable=True)
    question_1 = db.Column(db.Text, nullable=True)
    question_2 = db.Column(db.Text, nullable=True)
    question_3 = db.Column(db.Text, nullable=True)
    question_4 = db.Column(db.Text, nullable=True)
    question_5 = db.Column(db.Text, nullable=True)
    question_6 = db.Column(db.Text, nullable=True)
    question_7 = db.Column(db.Text, nullable=True)
    question_8 = db.Column(db.Text, nullable=True)
    question_9 = db.Column(db.Text, nullable=True)
    question_10 = db.Column(db.Text, nullable=True)
    score = db.Column(db.Integer, nullable=True)  # 0-10, computed from answer key on import; used for stats/queries
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=True)
    created_by_name = db.Column(db.String(255), nullable=True)
    created_by_email = db.Column(db.String(255), nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=True)
    updated_by_name = db.Column(db.String(255), nullable=True)
    updated_by_email = db.Column(db.String(255), nullable=True)

    participant = db.relationship('UserPII', foreign_keys=[email], primaryjoin='OptionalMcqResponse.email == UserPII.email', lazy='joined')

    def to_dict(self):
        return {
            'id': str(self.id),
            'track_number': self.track_number,
            'leader_name': self.leader_name,
            'email': self.email,
            'leader_phone': self.leader_phone,
            'team_size': self.team_size,
            'problem_statement': self.problem_statement,
            'question_1': self.question_1,
            'question_2': self.question_2,
            'question_3': self.question_3,
            'question_4': self.question_4,
            'question_5': self.question_5,
            'question_6': self.question_6,
            'question_7': self.question_7,
            'question_8': self.question_8,
            'question_9': self.question_9,
            'question_10': self.question_10,
            'score': self.score,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'created_by_name': self.created_by_name,
            'created_by_email': self.created_by_email,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'updated_by_name': self.updated_by_name,
            'updated_by_email': self.updated_by_email,
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
