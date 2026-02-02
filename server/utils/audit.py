"""
Audit context for master_logs (PostgreSQL triggers).
Sets session variables app.current_user and app.current_user_extra so
log_activity() can populate changed_by and additional_info.
"""
import json
from flask import g, has_request_context
from sqlalchemy import text

# Default when no user (unauthenticated, background job)
DEFAULT_AUDIT_USER = 'system'


def get_audit_user_identifier():
    """
    Return the string to store in master_logs.changed_by.
    Prefer email; fallback to user id; else DEFAULT_AUDIT_USER.
    """
    if not has_request_context():
        return DEFAULT_AUDIT_USER
    try:
        from server.utils.auth import get_current_user
        user = get_current_user()
        if user is None:
            return DEFAULT_AUDIT_USER
        return getattr(user, 'email', None) or str(getattr(user, 'id', '')) or DEFAULT_AUDIT_USER
    except Exception:
        return DEFAULT_AUDIT_USER


def set_audit_session_vars(user_identifier=None, additional_info=None):
    """
    Set PostgreSQL session variables for the current connection so
    log_activity() triggers can read changed_by and optional additional_info.
    Call before any audited write (or in before_request so every request has it).
    """
    from server.models import db
    identifier = user_identifier if user_identifier is not None else get_audit_user_identifier()
    # Sanitize: session variable must be a string; avoid breaking triggers
    safe_id = (identifier or DEFAULT_AUDIT_USER).strip()[:255]
    try:
        db.session.execute(
            text("SELECT set_config('app.current_user', :u, true)"),
            {"u": safe_id}
        )
    except Exception:
        pass
    if additional_info is not None:
        try:
            payload = json.dumps(additional_info) if isinstance(additional_info, dict) else str(additional_info)
            db.session.execute(
                text("SELECT set_config('app.current_user_extra', :e, true)"),
                {"e": payload[:32767]}
            )
        except Exception:
            pass


def set_audit_extra(extra):
    """
    Set additional_info for the current request's next audited operations.
    Use from routes (e.g. import) to add context like {"source": "csv_import", "filename": "..."}.
    """
    if not has_request_context():
        return
    if not hasattr(g, 'audit_extra'):
        g.audit_extra = {}
    if isinstance(extra, dict):
        g.audit_extra.update(extra)
    set_audit_session_vars(additional_info=g.audit_extra)
