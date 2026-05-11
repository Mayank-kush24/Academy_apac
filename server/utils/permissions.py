"""
Role-Based Access Control (RBAC) and page-level access decorators
"""
from functools import wraps
from flask import g, jsonify
from server.h2s_cdi_auth import get_module_pages
from server.utils.auth import get_current_user


def _portal_jwt_is_admin() -> bool:
    u = getattr(g, "user", None)
    return isinstance(u, dict) and bool(u.get("isAdmin"))


def _portal_jwt_active() -> bool:
    return isinstance(getattr(g, "user", None), dict)

# Page ids used in nav and allowed_pages. Slug is the path segment under /c/<cohort_id>/...
PAGES = [
    {'id': 'home', 'slug': None, 'path': '/', 'label': 'Home'},
    {'id': 'dashboard', 'slug': 'dashboard', 'path': '/c/<cohort>/dashboard', 'label': 'Dashboard'},
    {'id': 'profiles', 'slug': 'profiles', 'path': '/c/<cohort>/profiles', 'label': 'Profiles'},
    {'id': 'skill_lab_credits', 'slug': 'skill-lab-credits', 'path': '/c/<cohort>/skill-lab-credits', 'label': 'Skill Lab credits'},
    {'id': 'book_of_business', 'slug': 'book-of-business', 'path': '/c/<cohort>/book-of-business', 'label': 'Book of Business Registrations'},
    {'id': 'users_registrations', 'slug': 'users-registrations', 'path': '/c/<cohort>/users-registrations', 'label': 'Users'},
    {'id': 'skilllab_submission', 'slug': 'skilllab-submission', 'path': '/c/<cohort>/skilllab-submission', 'label': 'Skill Lab Submissions'},
    {'id': 'codelab_submission', 'slug': 'codelab-submission', 'path': '/c/<cohort>/codelab-submission', 'label': 'Code Lab Submissions'},
    {'id': 'project_submission', 'slug': 'project-submission', 'path': '/c/<cohort>/project-submission', 'label': 'Project Submissions'},
    {'id': 'optional_mcq_verification', 'slug': 'optional-mcq-verification', 'path': '/c/<cohort>/optional-mcq-verification', 'label': 'Optional MCQ Verification'},
    {'id': 'mcq_verification', 'slug': 'mcq-verification', 'path': '/c/<cohort>/mcq-verification', 'label': 'MCQ Verification'},
    {'id': 'track_progress_query', 'slug': 'track-progress-query', 'path': '/c/<cohort>/track-progress-query', 'label': 'Track Progress Query'},
    {'id': 'import', 'slug': 'import', 'path': '/c/<cohort>/import', 'label': 'Import Data'},
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
}


def can_access_page(user, page_id):
    """Return True if user is allowed to access the given page (by allowed_pages or role)."""
    if _portal_jwt_is_admin():
        return True
    if _portal_jwt_active():
        mod_pages = get_module_pages()
        if mod_pages is not None:
            if len(mod_pages) == 0:
                return False
            if page_id in mod_pages:
                return True
            from server.cdi_integration import portal_allowlist_allows_logical_page

            return portal_allowlist_allows_logical_page(mod_pages, page_id)
        return True
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
            if _portal_jwt_is_admin():
                return f(*args, **kwargs)
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
            if _portal_jwt_is_admin():
                return f(*args, **kwargs)
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
