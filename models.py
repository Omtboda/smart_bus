from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date, time
import json

db = SQLAlchemy()

class Admin(db.Model):
    __tablename__ = 'admins'
    
    admin_id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Student(db.Model):
    __tablename__ = 'students'
    
    student_id = db.Column(db.String(50), primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    department = db.Column(db.String(100), nullable=True)
    bus_no = db.Column(db.String(20), nullable=True)
    fee_status = db.Column(db.String(20), nullable=False, default='Pending') # 'Paid' or 'Pending'
    face_encoding = db.Column(db.Text, nullable=True)  # JSON-serialized list of 128 floats
    photo_path = db.Column(db.String(255), nullable=True)  # Path to stored photo
    
    # Relationships
    attendances = db.relationship('Attendance', backref='student', lazy=True)
    alerts = db.relationship('Alert', backref='student', lazy=True)
    
    def get_encoding(self):
        if self.face_encoding:
            return json.loads(self.face_encoding)
        return None
        
    def set_encoding(self, encoding_list):
        if encoding_list is not None:
            self.face_encoding = json.dumps(list(encoding_list))
        else:
            self.face_encoding = None

class Attendance(db.Model):
    __tablename__ = 'attendance'
    
    attendance_id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(50), db.ForeignKey('students.student_id', ondelete='SET NULL'), nullable=True)
    entry_date = db.Column(db.Date, nullable=False, default=date.today)
    entry_time = db.Column(db.Time, nullable=False, default=lambda: datetime.now().time())
    status = db.Column(db.String(20), nullable=False) # 'Allowed' or 'Denied'
    
    @property
    def formatted_time(self):
        return self.entry_time.strftime('%I:%M %p') if self.entry_time else ''
        
    @property
    def formatted_date(self):
        return self.entry_date.strftime('%Y-%m-%d') if self.entry_date else ''

class Alert(db.Model):
    __tablename__ = 'alerts'
    
    alert_id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(50), db.ForeignKey('students.student_id', ondelete='SET NULL'), nullable=True)
    alert_message = db.Column(db.String(255), nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.now)
    
    @property
    def formatted_timestamp(self):
        return self.timestamp.strftime('%Y-%m-%d %I:%M:%B %p') if self.timestamp else ''
        
    @property
    def short_time(self):
        return self.timestamp.strftime('%I:%M %p') if self.timestamp else ''
