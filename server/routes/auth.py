"""
Auth blueprint (CDI portal only).

There is no longer a local users table behind this endpoint. ``/api/auth/me``
returns the user view derived from the verified ``h2s_cdi_session`` JWT.
"""
from flask import Blueprint, jsonify

from server.utils.auth import get_current_user

bp = Blueprint("auth", __name__)


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
    """Return the JWT-derived user view, or 401 when unauthenticated."""
    user = get_current_user()
    if user is None:
        return jsonify({"error": "Authentication required"}), 401
    return jsonify({"user": user.to_dict()}), 200
