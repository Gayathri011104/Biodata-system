import os
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime


# Initialize Flask App
app = Flask(__name__)
app.config['SECRET_KEY'] = 'academic-biodata-secret-key-2024'
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'biodata_v2.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)
print("Database connected:", app.config['SQLALCHEMY_DATABASE_URI'])
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- Database Models ---

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False) # Register No for students
    password = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), nullable=False) # 'teacher' or 'student'

class StudentProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    reg_no = db.Column(db.String(20), unique=True, nullable=False) # Admission No (e.g. TL23BTCS0218)
    univ_no = db.Column(db.String(20), unique=True) # University No (e.g. VAS23CS0115)
    name = db.Column(db.String(100), nullable=False)
    # New Fields
    father_name = db.Column(db.String(100))
    mother_name = db.Column(db.String(100))
    gender = db.Column(db.String(10))
    blood_group = db.Column(db.String(5))
    email = db.Column(db.String(100))
    phone = db.Column(db.String(15))
    address = db.Column(db.Text)
    date_of_birth = db.Column(db.String(20))
    admission_year = db.Column(db.Integer)
    records = db.relationship('AcademicRecord', backref='student', lazy=True, cascade="all, delete-orphan")

class AcademicRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student_profile.id'), nullable=False)
    semester = db.Column(db.String(5), nullable=False) # S1, S2 ... S8
    attendance_percentage = db.Column(db.Float, default=0.0)
    internal_marks_json = db.Column(db.JSON) # Store {SubjectCode: Marks}
    result_status = db.Column(db.String(20)) # Pass/Fail/Pending
    sgpa = db.Column(db.Float)
    cgpa = db.Column(db.Float)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Integrated Parser Utility ---
from utils.parsers import process_academic_files

# --- Routes ---

@app.route('/')
def index():
    if not current_user.is_authenticated:
        return redirect(url_for('login'))
    return redirect(url_for('dashboard'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Invalid Credentials', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.role == 'teacher':
        sem = request.args.get('semester', 'S3')
        students = StudentProfile.query.all()
        # Attach semantic record to student object for easy template access
        display_data = []
        for s in students:
            rec = AcademicRecord.query.filter_by(student_id=s.id, semester=sem).first()
            display_data.append({'profile': s, 'record': rec})
        return render_template('teacher/dashboard.html', data=display_data, current_sem=sem)
    else:
        # Student View
        student = StudentProfile.query.filter_by(reg_no=current_user.username).first()
        return render_template('student/profile.html', student=student)

@app.route('/teacher/upload', methods=['GET', 'POST'])
@login_required
def upload_files():
    if current_user.role != 'teacher': return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        semester = request.form.get('semester')
        data_type = request.form.get('data_type', 'end_sem') # Get what type of marks this is
        files = request.files.getlist('files')
        
        if not files or files[0].filename == '':
            flash('No files selected', 'warning')
            return redirect(request.url)

        file_paths = []
        for file in files:
            filename = secure_filename(file.filename)
            path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(path)
            file_paths.append(path)

        # Integrated parsing logic
        success, message = process_academic_files(file_paths, semester, data_type, db, StudentProfile, AcademicRecord, User, generate_password_hash)
        
        if success:
            flash(f'Successfully processed files for {semester}: {message}', 'success')
        else:
            flash(f'Error processing: {message}', 'danger')
            
        return redirect(url_for('upload_files'))

    return render_template('teacher/upload.html')

@app.route('/teacher/attendance')
@login_required
def attendance_view():
    if current_user.role != 'teacher': return redirect(url_for('dashboard'))
    sem = request.args.get('semester', 'S3')
    records = AcademicRecord.query.filter_by(semester=sem).all()
    return render_template('teacher/attendance.html', records=records, current_sem=sem)

@app.route('/teacher/biodata')
@login_required
def biodata_list():
    if current_user.role != 'teacher': return redirect(url_for('dashboard'))
    students = StudentProfile.query.all()
    return render_template('teacher/biodata.html', students=students)

@app.route('/teacher/delete_student/<int:id>', methods=['POST'])
@login_required
def delete_student(id):
    if current_user.role != 'teacher': return redirect(url_for('dashboard'))
    student = StudentProfile.query.get_or_404(id)
    reg_no = student.reg_no
    
    # Delete associated user account
    user = User.query.filter_by(username=reg_no).first()
    if user:
        db.session.delete(user)
    
    db.session.delete(student)
    db.session.commit()
    flash(f'Student {reg_no} and associated records deleted.', 'success')
    return redirect(url_for('biodata_list'))

@app.route('/teacher/student/<int:id>')
@login_required
def student_detail(id):
    if current_user.role != 'teacher': return redirect(url_for('dashboard'))
    student = StudentProfile.query.get_or_404(id)
    # Get all 8 semesters data
    records = {r.semester: r for r in student.records}
    semesters = [f'S{i}' for i in range(1, 9)]
    return render_template('teacher/student_detail.html', student=student, records=records, semesters=semesters)

@app.route('/student/records')
@login_required
def student_records():
    if current_user.role != 'student': return redirect(url_for('dashboard'))
    student = StudentProfile.query.filter_by(reg_no=current_user.username).first()
    records = {r.semester: r for r in student.records}
    semesters = [f'S{i}' for i in range(1, 9)]
    return render_template('student/records.html', student=student, records=records, semesters=semesters)

@app.route('/student/update_profile', methods=['POST'])
@login_required
def update_profile():
    if current_user.role != 'student': return jsonify({'status': 'error'}), 403
    student = StudentProfile.query.filter_by(reg_no=current_user.username).first()
    student.phone = request.form.get('phone')
    student.address = request.form.get('address')
    student.email = request.form.get('email')
    # New Fields
    student.father_name = request.form.get('father_name')
    student.mother_name = request.form.get('mother_name')
    student.gender = request.form.get('gender')
    student.blood_group = request.form.get('blood_group')
    student.date_of_birth = request.form.get('date_of_birth')
    
    db.session.commit()
    flash('Profile updated successfully', 'success')
    return redirect(url_for('dashboard'))

# Helper to seeds dummy data for first run
def init_db():
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(username='admin').first():
            admin = User(username='admin', password=generate_password_hash('admin123'), role='teacher')
            db.session.add(admin)
            db.session.commit()

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000)
