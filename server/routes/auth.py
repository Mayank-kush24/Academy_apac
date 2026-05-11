"""
Authentication routes (CDI only — no password login).
"""
from flask import Blueprint, jsonify

from server.h2s_cdi_auth import get_session_payload_from_request
from server.utils.auth import get_current_user

bp = Blueprint("auth", __name__)


def _user_from_cdi_payload(payload: dict) -> dict:
    """Synthesize a User-like dict from the CDI JWT when no local User row exists."""
    is_admin = bool(payload.get("isAdmin"))
    email = (payload.get("email") or payload.get("sub") or "").strip()
    name = (payload.get("name") or "").strip() or (email or "Portal user")
    return {
        "id": str(payload.get("sub") or payload.get("user_id") or email or ""),
        "name": name,
        "email": email,
        "role": "admin" if is_admin else "viewer",
        "status": "active",
        "allowed_pages": None,
        "allowed_cohort_ids": None,
        "created_at": None,
        "_source": "cdi_jwt",
    }


@bp.route("/login", methods=["POST"])
def login():
    """Password login removed; use the CDI portal."""
    return (
        jsonify(
            {
                "error": "Password login is disabled. Open this app from the CDI dashboard "
                "or sign in at the portal."
            }
        ),
        410,
    )


@bp.route("/me", methods=["GET"])
def get_current_user_info():
    """
    Current user from h2s_cdi_session.
    Prefers a matching DB User; falls back to JWT info so the UI does not bounce to /login.
    """
    user = get_current_user()
    if user:
        return jsonify({"user": user.to_dict()}), 200

    payload = get_session_payload_from_request()
    if payload:
        return jsonify({"user": _user_from_cdi_payload(payload)}), 200

    return jsonify({"error": "Authentication required"}), 401
