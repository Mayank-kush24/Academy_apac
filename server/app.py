"""
Flask application initialization for Gen AI Academy APAC Edition
"""
import re

from flask import Flask, render_template, send_from_directory, request, jsonify, redirect, g, has_request_context, make_response, url_for
from flask_cors import CORS
from flask_compress import Compress
import os
import sys
import time

# Add parent directory to path if running directly
if __name__ == '__main__':
    parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)

from server.config import Config
from server.models import db, ActivityLog  # ActivityLog ensures activity_logs table is created
from server.routes import auth, import_data, dashboard, profiles, skilllab, book_of_business, users_registrations, skilllab_submission, codelab_submission, project_submission, mcq_verification, import_pii_injected, track_progress
from server.cohort_config import (
    cohort_list_for_template,
    cohort_disabled_pages,
    get_cohort_entry,
    is_cohort_html_page_disabled,
)
from server.utils.cohort_context import register_cohort_context
from server.utils.user_pii_combined_view import ensure_user_pii_combined_views

# URL slug (under /c/<id>/) -> Jinja template name
def _current_cohort_page_slug(path):
    m = re.match(r"^/c/\d+/(.+)$", path or "")
    return m.group(1) if m else None


class _StripPathPrefixMiddleware:
    """
    Some reverse proxies forward the full browser path as PATH_INFO (e.g. /apacacademy/)
    while Flask routes are mounted at /. Strip one physical prefix and set SCRIPT_NAME.
    """

    def __init__(self, wsgi_app, prefix: str):
        self.wsgi_app = wsgi_app
        self.prefix = (prefix or "").strip().rstrip("/")

    def __call__(self, environ, start_response):
        pfx = self.prefix
        if not pfx:
            return self.wsgi_app(environ, start_response)
        if not pfx.startswith("/"):
            pfx = "/" + pfx
        pi = environ.get("PATH_INFO") or "/"
        if pi != pfx and not pi.startswith(pfx + "/"):
            return self.wsgi_app(environ, start_response)
        rest = pi[len(pfx) :] or "/"
        if not rest.startswith("/"):
            rest = "/" + rest
        sn = (environ.get("SCRIPT_NAME") or "").rstrip("/")
        environ["SCRIPT_NAME"] = (sn + pfx) if sn else pfx
        if not environ["SCRIPT_NAME"].startswith("/"):
            environ["SCRIPT_NAME"] = "/" + environ["SCRIPT_NAME"].lstrip("/")
        environ["PATH_INFO"] = rest
        return self.wsgi_app(environ, start_response)


COHORT_PAGE_REGISTRY = {
    'dashboard': 'dashboard.html',
    'import': 'import.html',
    'import-user-pii-injected': 'import_user_pii_injected.html',
    'profiles': 'profiles.html',
    'skill-lab-credits': 'skill_lab_credits.html',
    'book-of-business': 'book_of_business.html',
    'users-registrations': 'users_registrations.html',
    'skilllab-submission': 'skilllab_submission.html',
    'codelab-submission': 'codelab_submission.html',
    'project-submission': 'project_submission.html',
    'optional-mcq-verification': 'optional_mcq_verification.html',
    'mcq-verification': 'mcq_verification.html',
    'track-progress-query': 'track_progress_query.html',
}

def create_app():
    """Create and configure Flask application"""
    # Get the directory of this file
    base_dir = os.path.dirname(os.path.abspath(__file__))
    app = Flask(__name__, 
                template_folder=os.path.join(base_dir, 'templates'),
                static_folder=os.path.join(base_dir, 'static'))

    from server.cdi_integration import (
        assert_cdi_auth_configured,
        build_cdi_path_page_rules,
        build_module_pages_for_portal,
        cdi_public_path_prefixes,
    )
    from server.h2s_cdi_auth import register_h2s_cdi_auth, register_with_portal, get_portal_url

    assert_cdi_auth_configured()

    _mount_pfx = ""
    _ar = (os.environ.get("APPLICATION_ROOT") or "").strip()
    if _ar:
        _mount_pfx = (_ar if _ar.startswith("/") else "/" + _ar).rstrip("/")
    else:
        _mid = (os.environ.get("H2S_CDI_MODULE_ID") or os.environ.get("JARVIS_MODULE_ID") or "").strip()
        if _mid:
            _mount_pfx = "/" + _mid.lower().replace(" ", "")

    from werkzeug.middleware.proxy_fix import ProxyFix

    _inner = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
    if _mount_pfx:
        app.wsgi_app = _StripPathPrefixMiddleware(_inner, _mount_pfx)
    else:
        app.wsgi_app = _inner

    @app.before_request
    def _apply_mount_script_name():
        prefix = request.environ.get("HTTP_X_FORWARDED_PREFIX", "").strip().rstrip("/")
        if prefix and not prefix.startswith("/"):
            prefix = "/" + prefix
        if not prefix and _mount_pfx:
            prefix = _mount_pfx
        if prefix:
            request.environ["SCRIPT_NAME"] = prefix

    register_h2s_cdi_auth(
        app,
        public_paths=cdi_public_path_prefixes(),
        path_page_rules=build_cdi_path_page_rules(),
        default_page=None,
    )

    @app.context_processor
    def inject_cdi_flags():
        try:
            from server.h2s_cdi_auth import get_portal_dashboard_url

            pu = get_portal_url().rstrip("/")
            return {
                "cdi_enabled": True,
                "cdi_portal_url": pu,
                "cdi_portal_login_url": f"{pu}/login" if pu else "",
                "cdi_portal_dashboard_url": get_portal_dashboard_url(),
            }
        except Exception:
            return {
                "cdi_enabled": True,
                "cdi_portal_url": "",
                "cdi_portal_login_url": "",
                "cdi_portal_dashboard_url": "",
            }
    
    # Load configuration
    app.config.from_object(Config)
    Config.init_app(app)
    
    # Enable CORS
    CORS(app)
    
    # Enable gzip/brotli compression for all responses
    Compress(app)

    # Cache-busting version injected into all templates (changes on restart / deploy)
    _asset_version = str(int(time.time()))

    @app.context_processor
    def inject_asset_version():
        cid = getattr(g, 'cohort_id', None) if has_request_context() else None
        entry = get_cohort_entry(cid) if cid is not None else None
        cslug = _current_cohort_page_slug(request.path) if has_request_context() else None
        sr = ''
        auth_me_url = '/api/auth/me'
        if has_request_context():
            sr = (request.script_root or '').rstrip('/')
            try:
                auth_me_url = url_for('auth.get_current_user_info')
            except Exception:
                auth_me_url = '/api/auth/me'
        cohort_path_prefix = f'{sr}/c/{cid}' if cid is not None else ''
        cohort_base_cohort1 = f'{sr}/c/1' if sr else '/c/1'
        return {
            'v': _asset_version,
            'cohort_id': cid,
            'cohort_label': (entry or {}).get('label') if entry else None,
            'cohorts_hub': cohort_list_for_template(),
            'current_cohort_page_slug': cslug,
            'app_path_prefix': sr,
            'cohort_path_prefix': cohort_path_prefix,
            'cohort_base_cohort1': cohort_base_cohort1,
            'auth_me_url': auth_me_url,
            'cohort_disabled_pages': cohort_disabled_pages(cid),
        }
    
    # Initialize database with connection pooling
    # Engine options are set in Config.init_app() via app.config['SQLALCHEMY_ENGINE_OPTIONS']
    # Flask-SQLAlchemy will use these options when creating the engine
    db.init_app(app)
    
    # Apply engine options after initialization (inside app context)
    with app.app_context():
        if 'SQLALCHEMY_ENGINE_OPTIONS' in app.config:
            engine_options = app.config['SQLALCHEMY_ENGINE_OPTIONS']
            # Update engine with connection pool settings
            try:
                if hasattr(db.engine, 'pool'):
                    db.engine.pool.size = engine_options.get('pool_size', 10)
                    db.engine.pool._max_overflow = engine_options.get('max_overflow', 20)
                    db.engine.pool._recycle = engine_options.get('pool_recycle', 3600)
                    db.engine.pool._pre_ping = engine_options.get('pool_pre_ping', True)
            except:
                # Engine might not be created yet, that's okay
                pass
    
    # Create tables
    with app.app_context():
        try:
            db.create_all()
            print("[OK] Database tables initialized")
        except Exception as e:
            print(f"[WARNING] Could not create database tables: {str(e)}")
            print("  Run 'python init_database.py' to initialize the database manually")
        try:
            ensure_user_pii_combined_views(db.engine)
        except Exception as e:
            print(f"[WARNING] user_pii_combined views: {e}")
        # Register activity log listeners (create/update/delete on cohort data tables)
        try:
            from server.utils.activity_log import register_activity_listeners
            register_activity_listeners()
            print("[OK] Activity log listeners registered")
        except Exception as e:
            print(f"[WARNING] Activity log listeners: {e}")
        # Pre-build dynamic cohort-bound model classes so concurrent first requests
        # don't race on SQLAlchemy's declarative registry (see warm_cohort_models docstring).
        try:
            from server.utils.cohort_participant_models import warm_cohort_models
            from server.models import (
                UserPII,
                UserPIICombined,
                UserPIIInjected,
                BobCompany,
                CreditLink,
                SkillboostProfile,
                SkillLabSubmission,
                CodeLabSubmission,
                ProjectSubmission,
                OptionalMcqVerification,
                OptionalMcqResponse,
                MainMcqResponse,
            )
            warm_cohort_models([
                UserPII,
                UserPIICombined,
                UserPIIInjected,
                BobCompany,
                CreditLink,
                SkillboostProfile,
                SkillLabSubmission,
                CodeLabSubmission,
                ProjectSubmission,
                OptionalMcqVerification,
                OptionalMcqResponse,
                MainMcqResponse,
            ])
            print("[OK] Cohort dynamic models pre-warmed")
        except Exception as e:
            print(f"[WARNING] warm_cohort_models: {e}")

    # Cohort search_path must run before any ORM / audit DB access on this connection.
    register_cohort_context(app)

    # Set PostgreSQL session variables for master_logs (changed_by, optional additional_info)
    @app.before_request
    def set_audit_context():
        try:
            from server.utils.audit import set_audit_session_vars
            set_audit_session_vars()
        except Exception:
            pass

    # Global error handler: log traceback for any *unhandled* exception so 500s
    # are diagnosable in the terminal. Routes that catch and return their own
    # ``jsonify({'error': str(e)})`` response are unaffected (the exception
    # never propagates to here).
    import traceback as _traceback
    from werkzeug.exceptions import HTTPException

    @app.errorhandler(Exception)
    def _log_unhandled_exception(exc):
        if isinstance(exc, HTTPException):
            return exc  # 404/403/etc. should pass through unchanged
        _traceback.print_exc()
        path = request.path if request else ''
        if path.startswith('/api/'):
            return jsonify({'error': 'Internal server error', 'detail': str(exc)}), 500
        if app.debug:
            # Let werkzeug's interactive debugger handle it.
            raise exc
        return jsonify({'error': 'Internal server error'}), 500

    # Register blueprints
    app.register_blueprint(auth.bp, url_prefix='/api/auth')
    app.register_blueprint(import_data.bp, url_prefix='/api/import')
    app.register_blueprint(dashboard.bp, url_prefix='/api/dashboard')
    app.register_blueprint(profiles.bp, url_prefix='/api/profiles')
    app.register_blueprint(skilllab.bp, url_prefix='/api/skilllab')
    app.register_blueprint(book_of_business.bp, url_prefix='/api/book-of-business')
    app.register_blueprint(users_registrations.bp, url_prefix='/api/users-registrations')
    app.register_blueprint(skilllab_submission.bp, url_prefix='/api/skilllab-submission')
    app.register_blueprint(codelab_submission.bp, url_prefix='/api/codelab-submission')
    app.register_blueprint(project_submission.bp, url_prefix='/api/project-submission')
    app.register_blueprint(mcq_verification.bp, url_prefix='/api/mcq-verification')
    app.register_blueprint(import_pii_injected.bp, url_prefix='/api/import-user-pii-injected')
    app.register_blueprint(track_progress.bp, url_prefix='/api/track-progress')
    
    # Serve static files with aggressive cache headers for faster repeat loads
    @app.route('/static/<path:filename>')
    def static_files(filename):
        """Serve static files with browser cache (24h for all assets)."""
        resp = send_from_directory(app.static_folder, filename)
        if resp.status_code == 200:
            lower = filename.lower()
            if lower.endswith(('.js', '.css', '.map')):
                resp.headers['Cache-Control'] = 'public, max-age=86400'
            elif lower.endswith(('.ico', '.png', '.jpg', '.jpeg', '.gif', '.webp', '.woff', '.woff2', '.ttf', '.eot')):
                resp.headers['Cache-Control'] = 'public, max-age=604800'
            fpath = os.path.join(app.static_folder, filename)
            try:
                mtime = str(int(os.path.getmtime(fpath)))
                resp.headers['ETag'] = f'"{mtime}"'
            except OSError:
                pass
        return resp
    
    # Home page (both / and /home; CDI portal redirects to /home by convention)
    @app.route('/')
    @app.route('/home')
    def home():
        """Home page"""
        return render_template('home.html')

    @app.route('/health')
    def health():
        return {
            "status": "ok",
            "module": os.environ.get("H2S_CDI_MODULE_ID", os.environ.get("JARVIS_MODULE_ID", "")),
        }, 200

    @app.route('/logout')
    def logout_page():
        r = make_response(redirect(get_portal_url().rstrip("/") + "/dashboard"))
        r.delete_cookie("h2s_cdi_session", path="/")
        return r

    @app.route('/login', methods=['GET', 'POST'])
    def login_page():
        if request.method == 'GET':
            return redirect(get_portal_url().rstrip('/') + '/login')
        return jsonify({'error': 'Sign in through the CDI portal.'}), 403
    
    @app.route('/c/<int:cohort_id>/<path:page_slug>')
    def cohort_workspace_page(cohort_id, page_slug):
        """Cohort-scoped UI pages (sidebar + data for that cohort)."""
        from flask import abort
        from server.cohort_config import ALLOWED_COHORT_IDS, is_cohort_enabled

        if cohort_id not in ALLOWED_COHORT_IDS or not is_cohort_enabled(cohort_id):
            abort(404)
        if is_cohort_html_page_disabled(cohort_id, page_slug):
            abort(404)
        template_name = COHORT_PAGE_REGISTRY.get(page_slug)
        if not template_name:
            abort(404)
        return render_template(template_name)

    # Legacy flat URLs → module home (so portals launching `…/dashboard` still land on home).
    @app.route('/dashboard')
    def legacy_dashboard():
        return redirect(url_for('home'), code=302)

    @app.route('/import')
    def legacy_import():
        return redirect(url_for('cohort_workspace_page', cohort_id=1, page_slug='import'), code=302)

    @app.route('/import-user-pii-injected')
    def legacy_import_pii_injected():
        return redirect(url_for('cohort_workspace_page', cohort_id=1, page_slug='import-user-pii-injected'), code=302)

    @app.route('/profiles')
    def legacy_profiles():
        return redirect(url_for('cohort_workspace_page', cohort_id=1, page_slug='profiles'), code=302)

    @app.route('/skill-lab-credits')
    def legacy_skill_lab_credits():
        return redirect(url_for('cohort_workspace_page', cohort_id=1, page_slug='skill-lab-credits'), code=302)

    @app.route('/book-of-business')
    def legacy_book_of_business():
        return redirect(url_for('cohort_workspace_page', cohort_id=1, page_slug='book-of-business'), code=302)

    @app.route('/users-registrations')
    def legacy_users_registrations():
        return redirect(url_for('cohort_workspace_page', cohort_id=1, page_slug='users-registrations'), code=302)

    @app.route('/skilllab-submission')
    def legacy_skilllab_submission():
        return redirect(url_for('cohort_workspace_page', cohort_id=1, page_slug='skilllab-submission'), code=302)

    @app.route('/codelab-submission')
    def legacy_codelab_submission():
        return redirect(url_for('cohort_workspace_page', cohort_id=1, page_slug='codelab-submission'), code=302)

    @app.route('/project-submission')
    def legacy_project_submission():
        return redirect(url_for('cohort_workspace_page', cohort_id=1, page_slug='project-submission'), code=302)

    @app.route('/optional-mcq-verification')
    def legacy_optional_mcq():
        return redirect(url_for('cohort_workspace_page', cohort_id=1, page_slug='optional-mcq-verification'), code=302)

    @app.route('/mcq-verification')
    def legacy_mcq_verification():
        return redirect(url_for('cohort_workspace_page', cohort_id=1, page_slug='mcq-verification'), code=302)

    @app.route('/track-progress-query')
    def legacy_track_progress_query():
        return redirect(url_for('cohort_workspace_page', cohort_id=1, page_slug='track-progress-query'), code=302)

    _port = int(os.environ.get('PORT', '3002'))
    _base = (os.environ.get('BASE_URL') or f'http://127.0.0.1:{_port}').rstrip('/')
    register_with_portal(
        build_module_pages_for_portal(),
        module_name=os.environ.get('MODULE_NAME', 'Gen AI Academy APAC'),
        base_url=_base,
    )

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=3002, debug=True)
