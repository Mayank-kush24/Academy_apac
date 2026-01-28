"""
Flask application initialization for Gen AI Academy APAC Edition
"""
from flask import Flask, render_template, send_from_directory
from flask_cors import CORS
import os
import sys

# Add parent directory to path if running directly
if __name__ == '__main__':
    parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)

from server.config import Config
from server.models import db
from server.routes import auth, users, import_data, dashboard, profiles

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
    
    # Register blueprints
    app.register_blueprint(auth.bp, url_prefix='/api/auth')
    app.register_blueprint(users.bp, url_prefix='/api/users')
    app.register_blueprint(import_data.bp, url_prefix='/api/import')
    app.register_blueprint(dashboard.bp, url_prefix='/api/dashboard')
    app.register_blueprint(profiles.bp, url_prefix='/api/profiles')
    
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
    
    # Login page
    @app.route('/login')
    def login_page():
        """Login page"""
        return render_template('login.html')
    
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
    
    return app


if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=3002, debug=True)
