"""
Flask application initialization for Gen AI Academy APAC Edition
"""
from flask import Flask, render_template, send_from_directory, request, jsonify, redirect
from flask_cors import CORS
import os
import sys

# Add parent directory to path if running directly
if __name__ == '__main__':
    parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)

from server.config import Config
from server.models import db, ActivityLog  # ActivityLog ensures activity_logs table is created
from server.routes import auth, users, import_data, dashboard, profiles, audit, skilllab

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
    
    # Serve static files
    @app.route('/static/<path:filename>')
    def static_files(filename):
        """Serve static files"""
        return send_from_directory(app.static_folder, filename)
    
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
    
    return app


if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=3002, debug=True)
