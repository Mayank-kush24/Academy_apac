"""
Flask application initialization for Gen AI Academy APAC Edition
"""
from flask import Flask, render_template, send_from_directory, request, jsonify, redirect
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
from server.routes import auth, users, import_data, dashboard, profiles, audit, skilllab, book_of_business, users_registrations, skilllab_submission, codelab_submission, mcq_verification, import_pii_injected, track_progress

def create_app():
    """Create and configure Flask application"""
    # Get the directory of this file
    base_dir = os.path.dirname(os.path.abspath(__file__))
    app = Flask(__name__, 
                template_folder=os.path.join(base_dir, 'templates'),
                static_folder=os.path.join(base_dir, 'static'))
    
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
        return {'v': _asset_version}
    
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
        # Ensure user_pii_combined is a VIEW (not a table left over from create_all)
        try:
            from sqlalchemy import text as _text
            inspector = db.inspect(db.engine)
            _all_tables = inspector.get_table_names()
            if 'user_pii_injected' in _all_tables:
                with db.engine.connect() as conn:
                    conn.execute(_text("DROP VIEW IF EXISTS user_pii_combined CASCADE"))
                    conn.execute(_text("DROP TABLE IF EXISTS user_pii_combined CASCADE"))
                    conn.execute(_text("""
                        CREATE VIEW user_pii_combined AS
                        SELECT id, registered_at, organization_name, class_stream, domain, designation, name, email,
                               mobile_number, country, state, city, date_of_birth, gender, occupation,
                               github_url, linkedin_url, utm_medium, bob_match, created_at, updated_at,
                               'user_pii' AS source
                        FROM user_pii
                        UNION ALL
                        SELECT id, registered_at, organization_name, class_stream, domain, designation, name, email,
                               mobile_number, country, state, city, date_of_birth, gender, occupation,
                               github_url, linkedin_url, utm_medium, bob_match, created_at, updated_at,
                               'user_pii_injected' AS source
                        FROM user_pii_injected i
                        WHERE NOT EXISTS (SELECT 1 FROM user_pii u WHERE u.email = i.email)
                    """))
                    conn.commit()
                print("[OK] user_pii_combined view created")
        except Exception as e:
            print(f"[WARNING] Could not create user_pii_combined view: {e}")
        # Register activity log listeners (create/update/delete on UserPII, User)
        try:
            from server.utils.activity_log import register_activity_listeners
            register_activity_listeners()
            print("[OK] Activity log listeners registered")
        except Exception as e:
            print(f"[WARNING] Activity log listeners: {e}")
    
    # Set PostgreSQL session variables for master_logs (changed_by, optional additional_info)
    # so triggers can record who made the change. Run before first DB use in request.
    @app.before_request
    def set_audit_context():
        try:
            from server.utils.audit import set_audit_session_vars
            set_audit_session_vars()
        except Exception:
            pass

    # Register blueprints
    app.register_blueprint(auth.bp, url_prefix='/api/auth')
    app.register_blueprint(users.bp, url_prefix='/api/users')
    app.register_blueprint(import_data.bp, url_prefix='/api/import')
    app.register_blueprint(dashboard.bp, url_prefix='/api/dashboard')
    app.register_blueprint(profiles.bp, url_prefix='/api/profiles')
    app.register_blueprint(audit.bp, url_prefix='/api/admin')
    app.register_blueprint(skilllab.bp, url_prefix='/api/skilllab')
    app.register_blueprint(book_of_business.bp, url_prefix='/api/book-of-business')
    app.register_blueprint(users_registrations.bp, url_prefix='/api/users-registrations')
    app.register_blueprint(skilllab_submission.bp, url_prefix='/api/skilllab-submission')
    app.register_blueprint(codelab_submission.bp, url_prefix='/api/codelab-submission')
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
    
    # Home page
    @app.route('/')
    def home():
        """Home page"""
        return render_template('home.html')
    
    # Login page (GET = show form, POST = accept form/JSON and return same as API for compatibility)
    @app.route('/login', methods=['GET', 'POST'])
    def login_page():
        if request.method != 'POST':
            return render_template('login.html')
        # POST: same logic as API so form or AJAX to /login works
        try:
            data = request.get_json(silent=True) or {}
            if not data:
                data = {'email': (request.form.get('email') or '').strip(), 'password': request.form.get('password') or ''}
            email = data.get('email') or ''
            password = data.get('password') or ''
            if not email or not password:
                return jsonify({'error': 'Email and password are required'}), 400
            from server.models import User
            import bcrypt
            from server.utils.auth import generate_token
            user = User.query.filter_by(email=email).first()
            if not user:
                return jsonify({'error': 'Invalid credentials'}), 401
            if user.status != 'active':
                return jsonify({'error': 'User account is inactive'}), 403
            pw_hash = user.password_hash
            if isinstance(pw_hash, str):
                pw_hash = pw_hash.encode('utf-8')
            if not bcrypt.checkpw(password.encode('utf-8'), pw_hash):
                return jsonify({'error': 'Invalid credentials'}), 401
            token = generate_token(user)
            return jsonify({'token': token, 'user': user.to_dict()}), 200
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    # Dashboard page
    @app.route('/dashboard')
    def dashboard_page():
        """Dashboard page"""
        return render_template('dashboard.html')
    
    # Import page
    @app.route('/import')
    def import_page():
        """Import data page"""
        return render_template('import.html')

    # Import User PII Injected (not on nav; access via URL only)
    @app.route('/import-user-pii-injected')
    def import_user_pii_injected_page():
        """Import into user_pii_injected table (no nav link)"""
        return render_template('import_user_pii_injected.html')
    
    # Users page (admin only - frontend will check)
    @app.route('/users')
    def users_page():
        """Users management page"""
        return render_template('users.html')
    
    # Profiles page (view user_pii data)
    @app.route('/profiles')
    def profiles_page():
        """User profiles page"""
        return render_template('profiles.html')

    # Skill Lab credits page
    @app.route('/skill-lab-credits')
    def skill_lab_credits_page():
        """Skill Lab credits page (Skill Lab / Skillboost profiles)"""
        return render_template('skill_lab_credits.html')

    # Book of Business Registrations page
    @app.route('/book-of-business')
    def book_of_business_page():
        """Book of Business Registrations (users with BOB match)"""
        return render_template('book_of_business.html')

    # Users (Registrations) page
    @app.route('/users-registrations')
    def users_registrations_page():
        """Users - all registered users (same stats/filters/columns as BOB)"""
        return render_template('users_registrations.html')

    # Skill Lab Submission Verification page
    @app.route('/skilllab-submission')
    def skilllab_submission_page():
        """Skill Lab Submission Verification (manual intern verification)"""
        return render_template('skilllab_submission.html')

    # Code Lab Submission Verification page
    @app.route('/codelab-submission')
    def codelab_submission_page():
        """Code Lab Submission Verification (manual intern verification)"""
        return render_template('codelab_submission.html')

    # Optional MCQ Verification page
    @app.route('/optional-mcq-verification')
    def optional_mcq_verification_page():
        """Optional MCQ Verification (manual verification of participant MCQ)"""
        return render_template('optional_mcq_verification.html')

    # Track Progress Query page
    @app.route('/track-progress-query')
    def track_progress_query_page():
        """Track Progress Query (filter users by grid status)"""
        return render_template('track_progress_query.html')
    
    return app


if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=3002, debug=True)
