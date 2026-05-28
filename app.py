from flask import Flask, render_template, Response, request, redirect, url_for, flash, session, jsonify
from config import Config
from models import db, Admin, Student, Attendance, Alert
from database_utils import init_db
from camera import VideoCamera
import os
import time
import face_recognition
from werkzeug.utils import secure_filename
from datetime import datetime, date

app = Flask(__name__)
app.config.from_object(Config)

# Initialize database
db.init_app(app)
init_db(app)

# Global camera instance (lazily initialized when video streaming starts)
global_camera = None

def get_camera():
    global global_camera
    if global_camera is None:
        global_camera = VideoCamera(app)
    return global_camera

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# Helper to require login
def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            flash('Please log in to access this page.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    if 'logged_in' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'logged_in' in session:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        admin = Admin.query.filter_by(username=username).first()
        if admin and admin.check_password(password):
            session['logged_in'] = True
            session['username'] = username
            flash('Successfully logged in!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password.', 'danger')
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    session.pop('username', None)
    flash('Successfully logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    # Counts
    total_students = Student.query.count()
    today = date.today()
    today_entries = Attendance.query.filter_by(entry_date=today, status='Allowed').count()
    pending_fee_count = Student.query.filter_by(fee_status='Pending').count()
    total_alerts_count = Alert.query.count()
    
    # Recent logs (limit 6)
    recent_logs = db.session.query(Attendance, Student)\
        .outerjoin(Student, Attendance.student_id == Student.student_id)\
        .order_by(Attendance.attendance_id.desc())\
        .limit(6).all()
        
    # Recent alerts
    recent_alerts = Alert.query.order_by(Alert.alert_id.desc()).limit(6).all()
    
    return render_template('dashboard.html', 
                           total_students=total_students,
                           today_entries=today_entries,
                           pending_fee_count=pending_fee_count,
                           total_alerts_count=total_alerts_count,
                           recent_logs=recent_logs,
                           recent_alerts=recent_alerts)

@app.route('/students', methods=['GET', 'POST'])
@login_required
def students():
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'add':
            student_id = request.form.get('student_id').strip().upper()
            name = request.form.get('name').strip()
            department = request.form.get('department').strip()
            bus_no = request.form.get('bus_no').strip()
            fee_status = request.form.get('fee_status')
            
            # Check duplication
            if Student.query.filter_by(student_id=student_id).first():
                flash(f'Student ID {student_id} already exists.', 'danger')
                return redirect(url_for('students'))
                
            # Process face file
            file = request.files.get('face_image')
            photo_path = None
            encoding_list = None
            
            if file and allowed_file(file.filename):
                filename = secure_filename(f"{student_id}.jpg")
                save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(save_path)
                photo_path = f"face_data/{filename}"
                
                # Perform face recognition processing to get 128D encoding
                try:
                    image = face_recognition.load_image_file(save_path)
                    encodings = face_recognition.face_encodings(image)
                    
                    if not encodings:
                        os.remove(save_path) # clean up
                        flash('No face detected in the photo. Please upload a clear close-up picture.', 'danger')
                        return redirect(url_for('students'))
                    elif len(encodings) > 1:
                        os.remove(save_path)
                        flash('Multiple faces detected. Please upload an image with only one face.', 'danger')
                        return redirect(url_for('students'))
                    else:
                        encoding_list = encodings[0].tolist()
                except Exception as e:
                    if os.path.exists(save_path):
                        os.remove(save_path)
                    flash(f'Error processing image: {e}', 'danger')
                    return redirect(url_for('students'))
            else:
                flash('Please upload a valid face photograph (.jpg, .jpeg, .png).', 'danger')
                return redirect(url_for('students'))
                
            # Save student
            new_student = Student(
                student_id=student_id,
                name=name,
                department=department,
                bus_no=bus_no,
                fee_status=fee_status,
                photo_path=photo_path
            )
            new_student.set_encoding(encoding_list)
            
            db.session.add(new_student)
            db.session.commit()
            
            # Reload encodings cache in camera
            cam = get_camera()
            cam.load_known_faces()
            
            flash(f'Student {name} registered successfully with face data!', 'success')
            
        elif action == 'edit':
            student_id = request.form.get('student_id')
            student = Student.query.filter_by(student_id=student_id).first()
            
            if student:
                student.name = request.form.get('name').strip()
                student.department = request.form.get('department').strip()
                student.bus_no = request.form.get('bus_no').strip()
                student.fee_status = request.form.get('fee_status')
                
                # Update image if uploaded
                file = request.files.get('face_image')
                if file and allowed_file(file.filename):
                    filename = secure_filename(f"{student_id}.jpg")
                    save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    file.save(save_path)
                    student.photo_path = f"face_data/{filename}"
                    
                    try:
                        image = face_recognition.load_image_file(save_path)
                        encodings = face_recognition.face_encodings(image)
                        
                        if not encodings:
                            flash('No face detected. Keeping previous face encoding.', 'warning')
                        elif len(encodings) > 1:
                            flash('Multiple faces detected. Keeping previous face encoding.', 'warning')
                        else:
                            student.set_encoding(encodings[0].tolist())
                    except Exception as e:
                        flash(f'Error processing image: {e}', 'danger')
                
                db.session.commit()
                
                # Reload cache in camera
                cam = get_camera()
                cam.load_known_faces()
                
                flash(f'Student {student.name} updated successfully.', 'success')
                
        elif action == 'delete':
            student_id = request.form.get('student_id')
            student = Student.query.filter_by(student_id=student_id).first()
            if student:
                name = student.name
                # Remove face photo if exists
                if student.photo_path:
                    abs_photo_path = os.path.join(app.config['BASE_DIR'], student.photo_path)
                    if os.path.exists(abs_photo_path):
                        try:
                            os.remove(abs_photo_path)
                        except Exception as e:
                            print(f"Error removing file: {e}")
                            
                db.session.delete(student)
                db.session.commit()
                
                # Reload cache in camera
                cam = get_camera()
                cam.load_known_faces()
                
                flash(f'Student {name} record deleted.', 'info')
                
        return redirect(url_for('students'))
        
    students_list = Student.query.all()
    return render_template('students.html', students=students_list)

@app.route('/live')
@login_required
def live():
    cam = get_camera()
    # List of all registered students for the simulation trigger drop-downs
    students_list = Student.query.all()
    return render_template('live.html', camera_type='Simulator' if cam.is_simulator else 'Hardware', students=students_list)

def gen(camera):
    """Generator function that yields processed frames from camera."""
    while True:
        frame = camera.get_frame()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n\r\n')
        time.sleep(0.04)  # ~25 FPS cap

@app.route('/video_feed')
def video_feed():
    cam = get_camera()
    return Response(gen(cam),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/attendance')
@login_required
def attendance():
    # Load all records
    records = db.session.query(Attendance, Student)\
        .outerjoin(Student, Attendance.student_id == Student.student_id)\
        .order_by(Attendance.attendance_id.desc()).all()
    return render_template('attendance.html', records=records)

@app.route('/alerts')
@login_required
def alerts():
    alerts_list = db.session.query(Alert, Student)\
        .outerjoin(Student, Alert.student_id == Student.student_id)\
        .order_by(Alert.alert_id.desc()).all()
    return render_template('alerts.html', alerts=alerts_list)

@app.route('/clear_alerts', methods=['POST'])
@login_required
def clear_alerts():
    try:
        db.session.query(Alert).delete()
        db.session.commit()
        flash('All alerts cleared successfully.', 'success')
    except Exception as e:
        flash(f'Error clearing alerts: {e}', 'danger')
    return redirect(url_for('alerts'))

# ----------------- API ENDPOINTS FOR AJAX -----------------

@app.route('/api/metrics')
@login_required
def api_metrics():
    total_students = Student.query.count()
    today = date.today()
    today_entries = Attendance.query.filter_by(entry_date=today, status='Allowed').count()
    pending_fee_count = Student.query.filter_by(fee_status='Pending').count()
    total_alerts_count = Alert.query.count()
    
    return jsonify({
        'total_students': total_students,
        'today_entries': today_entries,
        'pending_fee_count': pending_fee_count,
        'total_alerts_count': total_alerts_count
    })

@app.route('/api/recent_alerts')
@login_required
def api_recent_alerts():
    limit = request.args.get('limit', default=6, type=int)
    alerts = Alert.query.order_by(Alert.alert_id.desc()).limit(limit).all()
    
    alert_data = [{
        'id': a.alert_id,
        'student_id': a.student_id,
        'message': a.alert_message,
        'timestamp': a.timestamp.strftime('%H:%M:%S')
    } for a in alerts]
    
    return jsonify({'alerts': alert_data})

@app.route('/simulate_entry/<student_id>')
@login_required
def simulate_entry(student_id):
    cam = get_camera()
    name = None
    if student_id != 'unknown':
        student = Student.query.filter_by(student_id=student_id).first()
        if student:
            name = student.name
            
    cam.trigger_simulation(student_id)
    return jsonify({
        'status': 'success',
        'student_id': student_id,
        'name': name
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=True)
