"""
Role-Based Access Control (RBAC) decorators
"""
from functools import wraps
from flask import jsonify
from server.utils.auth import get_current_user


def require_role(*allowed_roles):
    """
    Decorator to require specific role(s) for access
    
    Usage:
        @require_role('admin')
        @require_role('admin', 'editor')
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user = get_current_user()
            if not user:
                return jsonify({'error': 'Authentication required'}), 401
            
            if user.status != 'active':
                return jsonify({'error': 'User account is inactive'}), 403
            
            if user.role not in allowed_roles:
                return jsonify({'error': 'Insufficient permissions'}), 403
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator
