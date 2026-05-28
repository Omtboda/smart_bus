from models import db, Admin, Student, Attendance, Alert
import os

def init_db(app):
    """Initializes the database, creating tables if they do not exist."""
    with app.app_context():
        # Create all tables (works for both SQLite and MySQL)
        db.create_all()
        
        # Check if Admin table is empty and seed default admin
        if not Admin.query.filter_by(username='admin').first():
            default_admin = Admin(username='admin')
            default_admin.set_password('admin123')
            db.session.add(default_admin)
            print("Default admin created: admin / admin123")
            
        # Check if Students table is empty and seed sample students
        if Student.query.count() == 0:
            samples = [
                Student(
                    student_id="STU001",
                    name="John Doe",
                    department="Computer Science",
                    bus_no="Bus 12",
                    fee_status="Paid",
                    face_encoding=None,
                    photo_path=None
                ),
                Student(
                    student_id="STU002",
                    name="Jane Smith",
                    department="Information Technology",
                    bus_no="Bus 12",
                    fee_status="Pending",
                    face_encoding=None,
                    photo_path=None
                ),
                Student(
                    student_id="STU003",
                    name="Robert Johnson",
                    department="Mechanical Eng.",
                    bus_no="Bus 08",
                    fee_status="Paid",
                    face_encoding=None,
                    photo_path=None
                ),
                Student(
                    student_id="STU004",
                    name="Alice Brown",
                    department="Electronics Eng.",
                    bus_no="Bus 08",
                    fee_status="Pending",
                    face_encoding=None,
                    photo_path=None
                )
            ]
            db.session.add_all(samples)
            print("Sample students seeded.")
            
        db.session.commit()
        print("Database initialized successfully.")
