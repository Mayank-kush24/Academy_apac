"""
User management routes (Admin only)
"""
from flask import Blueprint, request, jsonify
import bcrypt
from server.models import db, User
from server.utils.auth import get_current_user
from server.utils.permissions import require_role, PAGES

bp = Blueprint('users', __name__)


@bp.route('/pages', methods=['GET'])
@require_role('admin')
def get_pages():
    """Return list of pages for page-access UI (admin only)."""
    return jsonify({'pages': PAGES}), 200


@bp.route('', methods=['GET'])
@require_role('admin')
def get_users():
    """Get all users (admin only)"""
    try:
        users = User.query.all()
        return jsonify({
            'users': [user.to_dict() for user in users]
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('', methods=['POST'])
@require_role('admin')
def create_user():
    """Create a new user (admin only)"""
    try:
        data = request.get_json()
        name = data.get('name')
        email = data.get('email')
        password = data.get('password')
        role = data.get('role', 'viewer')
        status = data.get('status', 'active')
        allowed_pages = data.get('allowed_pages')  # list of page ids or None to use role defaults
        
        # Validation
        if not name or not email or not password:
            return jsonify({'error': 'Name, email, and password are required'}), 400
        
        if role not in ['admin', 'editor', 'viewer', 'support']:
            return jsonify({'error': 'Invalid role'}), 400
        
        if status not in ['active', 'inactive']:
            return jsonify({'error': 'Invalid status'}), 400
        
        valid_page_ids = {p['id'] for p in PAGES}
        if allowed_pages is not None:
            if not isinstance(allowed_pages, list):
                return jsonify({'error': 'allowed_pages must be a list'}), 400
            if not all(p in valid_page_ids for p in allowed_pages):
                return jsonify({'error': 'Invalid page id in allowed_pages'}), 400
        
        # Check if email already exists
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            return jsonify({'error': 'Email already exists'}), 400
        
        # Hash password
        password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        # Create user
        user = User(
            name=name,
            email=email,
            password_hash=password_hash,
            role=role,
            status=status,
            allowed_pages=allowed_pages if allowed_pages is not None else None
        )
        
        db.session.add(user)
        db.session.commit()
        
        return jsonify({
            'user': user.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@bp.route('/<user_id>', methods=['PUT'])
@require_role('admin')
def update_user(user_id):
    """Update a user (admin only)"""
    try:
        user = User.query.filter_by(id=user_id).first()
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        data = request.get_json()
        
        # Update fields if provided
        if 'name' in data:
            user.name = data['name']
        if 'email' in data:
            # Check if new email already exists
            existing_user = User.query.filter_by(email=data['email']).first()
            if existing_user and existing_user.id != user.id:
                return jsonify({'error': 'Email already exists'}), 400
            user.email = data['email']
        if 'password' in data and data['password']:
            # Hash new password
            user.password_hash = bcrypt.hashpw(
                data['password'].encode('utf-8'),
                bcrypt.gensalt()
            ).decode('utf-8')
        if 'role' in data:
            if data['role'] not in ['admin', 'editor', 'viewer', 'support']:
                return jsonify({'error': 'Invalid role'}), 400
            user.role = data['role']
        if 'status' in data:
            if data['status'] not in ['active', 'inactive']:
                return jsonify({'error': 'Invalid status'}), 400
            user.status = data['status']
        if 'allowed_pages' in data:
            val = data['allowed_pages']
            valid_page_ids = {p['id'] for p in PAGES}
            if val is None:
                user.allowed_pages = None
            elif isinstance(val, list):
                if not all(p in valid_page_ids for p in val):
                    return jsonify({'error': 'Invalid page id in allowed_pages'}), 400
                user.allowed_pages = val
            else:
                return jsonify({'error': 'allowed_pages must be a list or null'}), 400
        
        db.session.commit()
        
        return jsonify({
            'user': user.to_dict()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@bp.route('/<user_id>', methods=['DELETE'])
@require_role('admin')
def delete_user(user_id):
    """Delete a user (admin only)"""
    try:
        user = User.query.filter_by(id=user_id).first()
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Prevent deleting yourself
        current_user = get_current_user()
        if current_user and str(current_user.id) == user_id:
            return jsonify({'error': 'Cannot delete your own account'}), 400
        
        db.session.delete(user)
        db.session.commit()
        
        return jsonify({'message': 'User deleted successfully'}), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
