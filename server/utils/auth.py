"""
JWT authentication utilities
"""
from datetime import datetime, timedelta
from functools import wraps
from uuid import UUID
from flask import request, jsonify
from server.config import Config
from server.models import db, User

# Import PyJWT - check for correct package
try:
    import jwt
    # Verify it's PyJWT by checking for encode method
    if not hasattr(jwt, 'encode'):
        raise ImportError(
            "Wrong 'jwt' package installed. "
            "Please uninstall it and install PyJWT: "
            "pip uninstall jwt && pip install PyJWT==2.8.0"
        )
except ImportError as e:
    raise ImportError(
        "PyJWT is not installed. Please run: pip install PyJWT==2.8.0"
    ) from e


def generate_token(user):
    """Generate JWT token for user"""
    payload = {
        'user_id': str(user.id),
        'email': user.email,
        'role': user.role,
        'exp': datetime.utcnow() + timedelta(hours=Config.JWT_EXPIRATION_HOURS),
        'iat': datetime.utcnow()
    }
    # PyJWT 2.0+ returns bytes, convert to string
    token = jwt.encode(payload, Config.JWT_SECRET_KEY, algorithm='HS256')
    if isinstance(token, bytes):
        token = token.decode('utf-8')
    return token


def verify_token(token):
    """Verify JWT token and return payload"""
    try:
        payload = jwt.decode(token, Config.JWT_SECRET_KEY, algorithms=['HS256'])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def get_current_user():
    """Get current user from JWT token in request"""
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return None
    
    try:
        # Extract token from "Bearer <token>"
        token = auth_header.split(' ')[1]
        payload = verify_token(token)
        if not payload:
            return None
        
        # Get user from database (User.id is UUID, payload has string)
        user_id = payload.get('user_id')
        if not user_id:
            return None
        try:
            user_uuid = UUID(user_id) if isinstance(user_id, str) else user_id
        except (TypeError, ValueError):
            return None
        user = User.query.filter_by(id=user_uuid).first()
        return user
    except (IndexError, KeyError):
        return None


def token_required(f):
    """Decorator to require valid JWT token"""
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({'error': 'Authentication required'}), 401
        if user.status != 'active':
            return jsonify({'error': 'User account is inactive'}), 403
        return f(*args, **kwargs)
    return decorated
