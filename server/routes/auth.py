"""
Authentication routes
"""
from flask import Blueprint, request, jsonify
import bcrypt
from server.models import db, User
from server.utils.auth import generate_token, get_current_user
from server.utils.permissions import require_role

bp = Blueprint('auth', __name__)


@bp.route('/login', methods=['POST'])
def login():
    """User login endpoint"""
    try:
        data = request.get_json()
        email = data.get('email')
        password = data.get('password')
        
        if not email or not password:
            return jsonify({'error': 'Email and password are required'}), 400
        
        # Find user
        user = User.query.filter_by(email=email).first()
        if not user:
            return jsonify({'error': 'Invalid credentials'}), 401
        
        # Check status
        if user.status != 'active':
            return jsonify({'error': 'User account is inactive'}), 403
        
        # Verify password
        if not bcrypt.checkpw(password.encode('utf-8'), user.password_hash.encode('utf-8')):
            return jsonify({'error': 'Invalid credentials'}), 401
        
        # Generate token
        token = generate_token(user)
        
        return jsonify({
            'token': token,
            'user': user.to_dict()
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/me', methods=['GET'])
def get_current_user_info():
    """Get current authenticated user info"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Authentication required'}), 401
    
    return jsonify({
        'user': user.to_dict()
    }), 200
