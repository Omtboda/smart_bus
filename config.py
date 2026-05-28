import os

class Config:
    # Flask app configuration
    SECRET_KEY = os.environ.get('SECRET_KEY', 'smart-bus-access-fee-verification-secret-2026')
    
    # Path settings
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'face_data')
    
    # Ensure folders exist
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(os.path.join(BASE_DIR, 'database'), exist_ok=True)
    os.makedirs(os.path.join(BASE_DIR, 'attendance_logs'), exist_ok=True)
    
    # SQLite default database path
    sqlite_path = os.path.join(BASE_DIR, 'database', 'smart_bus.db')
    
    # Database configuration (Defaults to SQLite for zero-configuration, plug-and-play.
    # To switch to MySQL, set the environment variable DB_TYPE=mysql and configure DB parameters)
    DB_TYPE = os.environ.get('DB_TYPE', 'sqlite')
    
    if DB_TYPE == 'mysql':
        DB_USER = os.environ.get('DB_USER', 'root')
        DB_PASSWORD = os.environ.get('DB_PASSWORD', '')
        DB_HOST = os.environ.get('DB_HOST', 'localhost')
        DB_PORT = os.environ.get('DB_PORT', '3306')
        DB_NAME = os.environ.get('DB_NAME', 'smart_bus_db')
        SQLALCHEMY_DATABASE_URI = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    else:
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{sqlite_path}"
        
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # System verification settings
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
    FACE_RECOGNITION_TOLERANCE = 0.50  # Lower is stricter, higher is more loose
