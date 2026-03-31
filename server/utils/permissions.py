"""
Role-Based Access Control (RBAC) and page-level access decorators
"""
from functools import wraps
from flask import jsonify
from server.utils.auth import get_current_user

# Page ids used in nav and allowed_pages. When allowed_pages is set, user sees only these pages.
PAGES = [
    {'id': 'home', 'path': '/', 'label': 'Home'},
    {'id': 'dashboard', 'path': '/dashboard', 'label': 'Dashboard'},
    {'id': 'profiles', 'path': '/profiles', 'label': 'Profiles'},
    {'id': 'skill_lab_credits', 'path': '/skill-lab-credits', 'label': 'Skill Lab credits'},
    {'id': 'book_of_business', 'path': '/book-of-business', 'label': 'Book of Business Registrations'},
    {'id': 'users_registrations', 'path': '/users-registrations', 'label': 'Users'},
    {'id': 'skilllab_submission', 'path': '/skilllab-submission', 'label': 'Skill Lab Submissions'},
    {'id': 'codelab_submission', 'path': '/codelab-submission', 'label': 'Code Lab Submissions'},
    {'id': 'project_submission', 'path': '/project-submission', 'label': 'Project Submissions'},
    {'id': 'optional_mcq_verification', 'path': '/optional-mcq-verification', 'label': 'Optional MCQ Verification'},
    {'id': 'mcq_verification', 'path': '/mcq-verification', 'label': 'MCQ Verification'},
    {'id': 'track_progress_query', 'path': '/track-progress-query', 'label': 'Track Progress Query'},
    {'id': 'import', 'path': '/import', 'label': 'Import Data'},
    {'id': 'users', 'path': '/users', 'label': 'User Management'},
]

# Default roles that can access each page when allowed_pages is not set
# support: view-only access to home + profiles (use allowed_pages to restrict to those only)
DEFAULT_PAGE_ROLES = {
    'home': ['viewer', 'editor', 'admin', 'support'],
    'dashboard': ['viewer', 'editor', 'admin'],
    'profiles': ['viewer', 'editor', 'admin', 'support'],
    'skill_lab_credits': ['viewer', 'editor', 'admin'],
    'book_of_business': ['viewer', 'editor', 'admin'],
    'users_registrations': ['viewer', 'editor', 'admin'],
    'skilllab_submission': ['viewer', 'editor', 'admin'],
    'codelab_submission': ['viewer', 'editor', 'admin'],
    'project_submission': ['viewer', 'editor', 'admin'],
    'optional_mcq_verification': ['viewer', 'editor', 'admin'],
    'mcq_verification': ['viewer', 'editor', 'admin'],
    'track_progress_query': ['viewer', 'editor', 'admin'],
    'import': ['editor', 'admin'],
    'users': ['admin'],
}


def can_access_page(user, page_id):
    """Return True if user is allowed to access the given page (by allowed_pages or role)."""
    if not user or user.status != 'active':
        return False
    if user.allowed_pages is not None and len(user.allowed_pages) > 0:
        return page_id in user.allowed_pages
    roles = DEFAULT_PAGE_ROLES.get(page_id, [])
    return user.role in roles


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


def require_page_access(page_id):
    """
    Decorator to require access to a page. If user has allowed_pages set, checks page_id is in it;
    otherwise falls back to role (DEFAULT_PAGE_ROLES for that page).
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user = get_current_user()
            if not user:
                return jsonify({'error': 'Authentication required'}), 401
            if user.status != 'active':
                return jsonify({'error': 'User account is inactive'}), 403
            if not can_access_page(user, page_id):
                return jsonify({'error': 'Access not allowed to this page'}), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator
