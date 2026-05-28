import cv2
import numpy as np
import face_recognition
import time
import json
from datetime import datetime, date
from models import db, Student, Attendance, Alert

class VideoCamera:
    def __init__(self, app):
        self.app = app
        self.video = None
        self.is_simulator = False

        # Known face database cache
        self.known_face_encodings = []
        self.known_face_ids = []
        self.known_face_names = []
        self.known_face_fee_status = []
        self.known_face_depts = []
        self.known_face_bus_nos = []

        # Cache tolerance at init time — avoids current_app proxy in streaming thread
        with app.app_context():
            self.tolerance = app.config.get('FACE_RECOGNITION_TOLERANCE', 0.50)

        # Simulation variables
        self.simulated_student_id = None
        self.simulation_start_time = 0
        self.simulation_duration = 5.0

        # Debounce: rate-limit database writes per person
        self.last_log_time = {}
        self.log_cooldown = 10.0

        # Frame-skip face recognition — only process every Nth frame
        # This keeps the MJPEG stream smooth even on slow CPUs
        self.frame_count = 0
        self.process_every_n_frames = 3

        # Cached recognition results (drawn on skipped frames too)
        self._cached_face_locations = []
        self._cached_face_names = []
        self._cached_face_confidences = []
        self._cached_face_colors = []
        self._cached_face_statuses = []

        self.load_known_faces()
        self.init_camera()

    # ------------------------------------------------------------------
    # Camera Initialisation
    # ------------------------------------------------------------------

    def init_camera(self):
        """
        Opens the hardware webcam.
        Uses AVFoundation backend on macOS for reliable frame delivery,
        sets buffer to 1 so we always read the newest frame,
        and warms up with 10 discarded reads so the first real frame
        is never black.
        Falls back to Simulation Mode if the camera is unavailable.
        """
        try:
            # CAP_AVFOUNDATION is the correct macOS backend
            self.video = cv2.VideoCapture(0, cv2.CAP_AVFOUNDATION)

            if not self.video.isOpened():
                print("Warning: Could not open camera. Falling back to Simulation Mode.")
                self.is_simulator = True
                return

            # Keep buffer small so frames are always fresh (no stale backlog)
            self.video.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            # Warm-up: read and discard 20 frames.
            # On macOS the first N frames are often black while the sensor adjusts.
            print("Camera warming up…")
            for _ in range(20):
                ok, _ = self.video.read()
                if not ok:
                    break

            # Final sanity check — must get a non-black frame
            ok, test_frame = self.video.read()
            if not ok or test_frame is None:
                print("Warning: Camera opened but returned no frame. Falling back to Simulation Mode.")
                self.video.release()
                self.is_simulator = True
                return

            print("Camera initialised successfully (hardware mode).")

        except Exception as e:
            print(f"Camera error: {e}. Falling back to Simulation Mode.")
            self.is_simulator = True

    # ------------------------------------------------------------------
    # Face Database
    # ------------------------------------------------------------------

    def load_known_faces(self):
        """Loads face encodings from the database into memory."""
        with self.app.app_context():
            students = Student.query.filter(Student.face_encoding.isnot(None)).all()
            self.known_face_encodings = []
            self.known_face_ids = []
            self.known_face_names = []
            self.known_face_fee_status = []
            self.known_face_depts = []
            self.known_face_bus_nos = []

            for student in students:
                encoding = student.get_encoding()
                if encoding:
                    self.known_face_encodings.append(np.array(encoding))
                    self.known_face_ids.append(student.student_id)
                    self.known_face_names.append(student.name)
                    self.known_face_fee_status.append(student.fee_status)
                    self.known_face_depts.append(student.department)
                    self.known_face_bus_nos.append(student.bus_no)

            print(f"Loaded {len(self.known_face_encodings)} face encoding(s) from database.")

    # ------------------------------------------------------------------
    # Simulation
    # ------------------------------------------------------------------

    def trigger_simulation(self, student_id):
        self.simulated_student_id = student_id
        self.simulation_start_time = time.time()
        print(f"Simulation triggered for: {student_id}")

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def log_entry(self, student_id, name, fee_status, status):
        """Writes an attendance record + optional alert, rate-limited per person."""
        now = time.time()
        key = student_id if student_id else 'unknown'

        if key in self.last_log_time and (now - self.last_log_time[key]) < self.log_cooldown:
            return

        self.last_log_time[key] = now

        with self.app.app_context():
            db.session.add(Attendance(student_id=student_id, status=status))

            if status == 'Denied':
                if fee_status == 'Pending':
                    msg = f"Fee Pending — Entry Denied for {name} ({student_id or 'Unknown'})"
                else:
                    msg = "Unauthorized Person Detected"
                db.session.add(Alert(student_id=student_id, alert_message=msg))

            db.session.commit()
            print(f"Logged: {name} | {status} | Fee: {fee_status}")

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def __del__(self):
        if self.video is not None:
            self.video.release()

    # ------------------------------------------------------------------
    # Frame Capture & Recognition
    # ------------------------------------------------------------------

    def get_frame(self):
        """
        Returns one JPEG-encoded frame for the MJPEG stream.

        Hardware mode:
          - Reads a fresh frame from the webcam
          - Runs face recognition every N frames (cached results shown in between)
          - Draws HUD overlays on every frame

        Simulator mode:
          - Draws a dark placeholder canvas
          - If a simulation is active, renders a mock face box
        """
        # ── Check active simulation ──────────────────────────────────
        is_simulating_active = False
        sim_student_id = None
        if self.simulated_student_id:
            if time.time() - self.simulation_start_time < self.simulation_duration:
                is_simulating_active = True
                sim_student_id = self.simulated_student_id
            else:
                self.simulated_student_id = None
                self._cached_face_locations = []   # clear overlay when sim ends

        # ── Grab frame ───────────────────────────────────────────────
        if self.is_simulator:
            frame = self._build_simulator_frame(is_simulating_active)
        else:
            ok, frame = self.video.read()
            if not ok or frame is None:
                # Camera dropped — return a one-off error frame
                err = np.zeros((480, 640, 3), dtype=np.uint8)
                cv2.putText(err, "Camera Disconnected — Restart the server",
                            (60, 240), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
                _, jpeg = cv2.imencode('.jpg', err)
                return jpeg.tobytes()

        # ── Face Recognition (hardware mode only, every N frames) ────
        if not self.is_simulator:
            self.frame_count += 1
            if self.frame_count % self.process_every_n_frames == 0:
                self._run_recognition(frame)

        # ── Simulation overlay (sim mode only) ───────────────────────
        elif is_simulating_active:
            self._run_simulation_overlay(sim_student_id)

        # ── Draw cached HUD results onto the frame ───────────────────
        self._draw_hud(frame)

        # ── Encode to JPEG ───────────────────────────────────────────
        _, jpeg = cv2.imencode('.jpg', frame)
        return jpeg.tobytes()

    # ------------------------------------------------------------------
    # Internal Helpers
    # ------------------------------------------------------------------

    def _build_simulator_frame(self, is_simulating_active):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.rectangle(frame, (10, 10), (630, 470), (45, 30, 20), 2)
        cv2.putText(frame, "SMART BUS HUD — SIMULATOR MODE",
                    (90, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (120, 120, 120), 1)
        if is_simulating_active:
            cv2.putText(frame, "SIMULATING BOARDING...",
                        (30, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 255), 1)
        else:
            cv2.putText(frame, "STATUS: STANDBY — Use Control Panel to Simulate",
                        (30, 240), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (90, 90, 90), 1)
        return frame

    def _run_recognition(self, frame):
        """Runs face_recognition on a downscaled copy and caches results."""
        # Scale down 4× for speed
        small = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
        rgb_small = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)

        locations_small = face_recognition.face_locations(rgb_small)
        encodings = face_recognition.face_encodings(rgb_small, locations_small)

        # Scale locations back to full resolution
        locations_full = [(t*4, r*4, b*4, l*4) for t, r, b, l in locations_small]

        names, confidences, colors, statuses = [], [], [], []

        for enc in encodings:
            name, confidence, fee_status, status, student_id = \
                "Unknown", 0.0, "Unknown", "Denied", None

            if self.known_face_encodings:
                matches = face_recognition.compare_faces(
                    self.known_face_encodings, enc, tolerance=self.tolerance)
                distances = face_recognition.face_distance(self.known_face_encodings, enc)

                if len(distances) > 0:
                    best = int(np.argmin(distances))
                    dist = distances[best]
                    if matches[best] and dist <= self.tolerance:
                        student_id  = self.known_face_ids[best]
                        name        = self.known_face_names[best]
                        fee_status  = self.known_face_fee_status[best]
                        confidence  = (1.0 - dist) * 100
                        status      = 'Allowed' if fee_status == 'Paid' else 'Denied'

            if status == 'Allowed':
                color, msg = (0, 255, 0), "Student Verified - Entry Allowed"
            elif fee_status == 'Pending':
                color, msg = (0, 0, 255), "Fee Pending - Entry Denied"
            else:
                color, msg, confidence = (0, 0, 255), "Unauthorized Person Detected", 0.0

            names.append(name)
            confidences.append(confidence)
            colors.append(color)
            statuses.append(msg)

            self.log_entry(student_id, name, fee_status, status)

        # Update cache
        self._cached_face_locations  = locations_full
        self._cached_face_names      = names
        self._cached_face_confidences = confidences
        self._cached_face_colors     = colors
        self._cached_face_statuses   = statuses

    def _run_simulation_overlay(self, sim_student_id):
        """Builds cached overlay data for a simulated boarding scan."""
        top, right, bottom, left = 120, 440, 360, 200

        with self.app.app_context():
            if sim_student_id == 'unknown':
                name, fee_status, student_id, confidence, status = \
                    "Unknown", "Unknown", None, 0.0, "Denied"
            else:
                s = Student.query.filter_by(student_id=sim_student_id).first()
                if s:
                    name, fee_status, student_id = s.name, s.fee_status, s.student_id
                    confidence = 94.5
                    status = 'Allowed' if fee_status == 'Paid' else 'Denied'
                else:
                    name, fee_status, student_id, confidence, status = \
                        "Unknown", "Unknown", None, 0.0, "Denied"

        if status == 'Allowed':
            color, msg = (0, 255, 0), "Student Verified - Entry Allowed"
        elif fee_status == 'Pending':
            color, msg = (0, 0, 255), "Fee Pending - Entry Denied"
        else:
            color, msg, confidence = (0, 0, 255), "Unauthorized Person Detected", 0.0

        self._cached_face_locations  = [(top, right, bottom, left)]
        self._cached_face_names      = [name]
        self._cached_face_confidences = [confidence]
        self._cached_face_colors     = [color]
        self._cached_face_statuses   = [msg]

        self.log_entry(student_id, name, fee_status, status)

    def _draw_hud(self, frame):
        """Draws the cached face boxes and labels onto the frame in-place."""
        h, w = frame.shape[:2]

        for (top, right, bottom, left), name, conf, color, msg in zip(
                self._cached_face_locations,
                self._cached_face_names,
                self._cached_face_confidences,
                self._cached_face_colors,
                self._cached_face_statuses):

            # Clamp coordinates to frame dimensions
            top    = max(0, top);    left  = max(0, left)
            bottom = min(h, bottom); right = min(w, right)

            # Main bounding box
            cv2.rectangle(frame, (left, top), (right, bottom), color, 2)

            # Corner accent lines (futuristic HUD style)
            L = 20
            for pt1, pt2 in [
                ((left, top),    (left+L, top)),    ((left, top),    (left, top+L)),
                ((right, top),   (right-L, top)),   ((right, top),   (right, top+L)),
                ((left, bottom), (left+L, bottom)), ((left, bottom), (left, bottom-L)),
                ((right,bottom), (right-L,bottom)), ((right,bottom), (right,bottom-L)),
            ]:
                cv2.line(frame, pt1, pt2, color, 3)

            # Text panel background
            y = bottom + 25 if bottom + 70 < h else top - 15
            cv2.rectangle(frame, (left-2, y-18), (right+2, y+45), (15, 15, 15), -1)
            cv2.rectangle(frame, (left-2, y-18), (right+2, y+45), color, 1)

            # Name + confidence
            label = f"{name} ({conf:.1f}%)" if conf > 0 else name
            cv2.putText(frame, label, (left+5, y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)

            # Status message
            cv2.putText(frame, msg, (left+5, y+20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1, cv2.LINE_AA)

            # Timestamp
            ts = datetime.now().strftime('%H:%M:%S')
            cv2.putText(frame, f"TIME: {ts}", (left+5, y+38),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.35, (180, 180, 180), 1, cv2.LINE_AA)
