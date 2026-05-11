"""
Authentication: CDI portal cookie only (h2s_cdi_session → local User by email).
"""
from functools import wraps
from flask import request, jsonify
from sqlalchemy import func
from server.models import User


def get_current_user():
    """Resolve app User from verified CDI JWT in the h2s_cdi_session cookie."""
    try:
        from server.h2s_cdi_auth import get_session_payload_from_request

        cdi_payload = get_session_payload_from_request()
        if not cdi_payload:
            return None
        email = (cdi_payload.get("email") or cdi_payload.get("sub") or "").strip()
        if not email:
            return None
        user = User.query.filter(func.lower(User.email) == email.lower()).first()
        if user and user.status == "active":
            return user
    except Exception:
        return None
    return None


def token_required(f):
    """Require a valid CDI session mapping to an active User (legacy name)."""

    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({"error": "Authentication required"}), 401
        if user.status != "active":
            return jsonify({"error": "User account is inactive"}), 403
        return f(*args, **kwargs)

    return decorated
