"""
Configuration management for Flask application
"""
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    """Application configuration"""
    
    # Database configuration
    DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://user:password@localhost:5432/academy_db')
    SQLALCHEMY_DATABASE_URI = DATABASE_URL
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Database connection pooling for performance
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': int(os.getenv('DB_POOL_SIZE', '10')),  # Number of connections to maintain
        'max_overflow': int(os.getenv('DB_MAX_OVERFLOW', '20')),  # Max connections beyond pool_size
        'pool_pre_ping': True,  # Verify connections before using
        'pool_recycle': int(os.getenv('DB_POOL_RECYCLE', '3600')),  # Recycle connections after 1 hour
        'echo': os.getenv('DB_ECHO', 'False').lower() == 'true'  # Log SQL queries (disable in production)
    }
    
    # JWT configuration
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'change-this-secret-key-in-production')
    JWT_EXPIRATION_HOURS = int(os.getenv('JWT_EXPIRATION_HOURS', '24'))
    
    # Flask configuration
    SECRET_KEY = os.getenv('FLASK_SECRET_KEY', 'change-this-flask-secret-key-in-production')
    
    # File upload configuration (None = no limit)
    MAX_CONTENT_LENGTH = None
    UPLOAD_FOLDER = 'uploads'
    
    @staticmethod
    def init_app(app):
        """Initialize application with configuration"""
        # Create upload folder if it doesn't exist
        upload_folder = os.path.join(os.path.dirname(os.path.dirname(__file__)), Config.UPLOAD_FOLDER)
        if not os.path.exists(upload_folder):
            os.makedirs(upload_folder)
        
        # Apply SQLAlchemy engine options
        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = Config.SQLALCHEMY_ENGINE_OPTIONS
