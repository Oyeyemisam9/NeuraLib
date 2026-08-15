from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, abort, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
import os
from functools import wraps
from sqlalchemy import func
import secrets
import string
from flask_mail import Mail, Message
from sqlalchemy.sql import or_
import uuid
from flask_wtf.csrf import CSRFProtect

# Try to import Flask-Limiter, but make it optional
try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
    LIMITER_AVAILABLE = True
except ImportError:
    LIMITER_AVAILABLE = False
    print("Warning: Flask-Limiter not installed. Rate limiting will be disabled.")

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-here')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///neuralib.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Email configuration
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER')

# Initialize CSRF protection
csrf = CSRFProtect(app)

# Initialize rate limiter if available
if LIMITER_AVAILABLE:
    limiter = Limiter(
        app=app,
        key_func=get_remote_address,
        default_limits=["200 per day", "50 per hour"],
        storage_uri="redis://localhost:6379"
    )
else:
    # Create a dummy limiter decorator that does nothing
    def dummy_limiter(*args, **kwargs):
        def decorator(f):
            return f
        return decorator
    limiter = type('DummyLimiter', (), {'limit': dummy_limiter})

ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'txt'}

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize extensions
db = SQLAlchemy()
login_manager = LoginManager()
mail = Mail()

# Initialize the app with the extensions
db.init_app(app)
login_manager.init_app(app)
mail.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'info'

# Database Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    is_admin = db.Column(db.Boolean, default=False)
    bio = db.Column(db.Text)
    department = db.Column(db.String(100))
    student_id = db.Column(db.String(20))
    materials = db.relationship('Material', backref='uploader', lazy=True)
    comments = db.relationship('Comment', backref='author', lazy=True)
    ratings = db.relationship('Rating', backref='user', lazy=True)
    is_verified = db.Column(db.Boolean, default=False)
    verification_token = db.Column(db.String(128))
    verification_token_expiry = db.Column(db.DateTime)
    reset_token = db.Column(db.String(128))
    reset_token_expiry = db.Column(db.DateTime)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    department = db.Column(db.String(100), nullable=False)
    level = db.Column(db.String(20), nullable=False)  # 100, 200, 300, 400
    materials = db.relationship('Material', backref='course', lazy=True)

class Material(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    filename = db.Column(db.String(255), nullable=False)
    category = db.Column(db.String(50), nullable=False)  # course_outline, manual, pdf
    level = db.Column(db.String(20), nullable=False)  # 100, 200, 300, 400
    upload_date = db.Column(db.DateTime, default=datetime.utcnow)
    uploaded_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'))
    comments = db.relationship('Comment', backref='material', lazy=True)
    ratings = db.relationship('Rating', backref='material', lazy=True)
    downloads = db.Column(db.Integer, default=0)

    @property
    def average_rating(self):
        return db.session.query(func.avg(Rating.value)).filter_by(material_id=self.id).scalar() or 0

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    date_posted = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    material_id = db.Column(db.Integer, db.ForeignKey('material.id'))

class Rating(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    value = db.Column(db.Integer, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    material_id = db.Column(db.Integer, db.ForeignKey('material.id'))
    __table_args__ = (db.UniqueConstraint('user_id', 'material_id'),)

# Helper Functions
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def generate_verification_token():
    return secrets.token_urlsafe(32)

def generate_password_reset_token():
    return secrets.token_urlsafe(32)

def send_verification_email(user):
    token = generate_verification_token()
    user.verification_token = token
    user.verification_token_expiry = datetime.utcnow() + timedelta(hours=24)
    db.session.commit()
    
    msg = Message('Verify Your Email',
                  recipients=[user.email])
    msg.body = f'''To verify your email, visit the following link:
{url_for('verify_email', token=token, _external=True)}

If you did not make this request then simply ignore this email.
'''
    mail.send(msg)

def send_password_reset_email(user):
    token = generate_password_reset_token()
    user.reset_token = token
    user.reset_token_expiry = datetime.utcnow() + timedelta(hours=1)
    db.session.commit()
    
    msg = Message('Password Reset Request',
                  recipients=[user.email])
    msg.body = f'''To reset your password, visit the following link:
{url_for('reset_password', token=token, _external=True)}

If you did not make this request then simply ignore this email.
'''
    mail.send(msg)

def validate_password(password):
    """Validate password strength"""
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    if not any(c.isupper() for c in password):
        return False, "Password must contain at least one uppercase letter"
    if not any(c.islower() for c in password):
        return False, "Password must contain at least one lowercase letter"
    if not any(c.isdigit() for c in password):
        return False, "Password must contain at least one number"
    if not any(c in string.punctuation for c in password):
        return False, "Password must contain at least one special character"
    return True, "Password is strong"

def generate_unique_filename(filename):
    """Generate a unique filename to prevent collisions"""
    ext = filename.rsplit('.', 1)[1].lower()
    return f"{uuid.uuid4().hex}.{ext}"

# Routes
@app.route('/')
def landing():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    return render_template('landing.html')

@app.route('/home')
@login_required
def home():
    # Get search and filter parameters
    search_query = request.args.get('search', '')
    category = request.args.get('category', '')
    level = request.args.get('level', '')
    course_id = request.args.get('course', type=int)

    # Base query
    query = Material.query

    # Apply filters
    if search_query:
        query = query.filter(
            or_(
                Material.title.ilike(f'%{search_query}%'),
                Material.description.ilike(f'%{search_query}%')
            )
        )
    
    if category:
        query = query.filter(Material.category == category)
    
    if level:
        query = query.filter(Material.level == level)
    
    if course_id:
        query = query.filter(Material.course_id == course_id)

    # Get materials with pagination
    page = request.args.get('page', 1, type=int)
    materials = query.order_by(Material.upload_date.desc()).paginate(
        page=page, per_page=12, error_out=False
    )

    # Get all courses for the filter dropdown
    courses = Course.query.order_by(Course.code).all()

    # Get recommendations for logged-in users
    recommendations = []
    if current_user.is_authenticated:
        # Get user's department
        user_department = current_user.department

        # Create a subquery to calculate average ratings
        avg_ratings = db.session.query(
            Rating.material_id,
            func.avg(Rating.value).label('avg_rating')
        ).group_by(Rating.material_id).subquery()

        # Query materials from the same department with their average ratings
        rec_query = Material.query.join(Course).filter(Course.department == user_department)\
            .outerjoin(avg_ratings, Material.id == avg_ratings.c.material_id)\
            .order_by(avg_ratings.c.avg_rating.desc().nullslast())
        
        # Get top rated materials
        recommendations = rec_query.limit(4).all()

    return render_template('index.html',
                         materials=materials,
                         courses=courses,
                         recommendations=recommendations)

@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute") if LIMITER_AVAILABLE else lambda x: x
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    
    if request.method == 'POST':
        try:
            username = request.form.get('username')
            password = request.form.get('password')
            remember = request.form.get('remember', False)

            if not username or not password:
                flash('Please enter both username and password', 'danger')
                return render_template('login.html')

            user = User.query.filter_by(username=username).first()
            
            if user and user.check_password(password):
                login_user(user, remember=remember)
                next_page = request.args.get('next')
                if not next_page or not next_page.startswith('/'):
                    next_page = url_for('home')
                return redirect(next_page)
            else:
                flash('Invalid username or password', 'danger')
                return render_template('login.html')
        except Exception as e:
            flash('An error occurred during login. Please try again.', 'danger')
            print(f"Login error: {str(e)}")
            return render_template('login.html')

    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
@limiter.limit("10 per hour") if LIMITER_AVAILABLE else lambda x: x
def register():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    
    if request.method == 'POST':
        try:
            # Get form data
            username = request.form.get('username')
            email = request.form.get('email')
            password = request.form.get('password')
            confirm_password = request.form.get('confirm_password')
            student_id = request.form.get('student_id')
            department = request.form.get('department')

            # Debug print
            print(f"Form data received: username={username}, email={email}, student_id={student_id}, department={department}")

            # Validate input
            if not all([username, email, password, confirm_password, student_id, department]):
                missing_fields = []
                if not username: missing_fields.append('username')
                if not email: missing_fields.append('email')
                if not password: missing_fields.append('password')
                if not confirm_password: missing_fields.append('confirm_password')
                if not student_id: missing_fields.append('student_id')
                if not department: missing_fields.append('department')
                flash(f'Missing required fields: {", ".join(missing_fields)}', 'danger')
                return render_template('register.html')

            # Check if username or email already exists
            if User.query.filter_by(username=username).first():
                flash('Username already exists', 'danger')
                return render_template('register.html')
            
            if User.query.filter_by(email=email).first():
                flash('Email already registered', 'danger')
                return render_template('register.html')

            # Validate password
            is_valid, message = validate_password(password)
            if not is_valid:
                flash(message, 'danger')
                return render_template('register.html')

            # Check if passwords match
            if password != confirm_password:
                flash('Passwords do not match', 'danger')
                return render_template('register.html')

            # Create new user
            user = User(
                username=username,
                email=email,
                student_id=student_id,
                department=department,
                is_verified=True  # Set to True by default
            )
            user.set_password(password)

            # Add to database
            db.session.add(user)
            db.session.commit()

            flash('Registration successful! You can now log in.', 'success')
            return redirect(url_for('login'))

        except Exception as e:
            db.session.rollback()
            print(f"Registration error: {str(e)}")
            flash('An error occurred during registration. Please try again.', 'danger')
            return render_template('register.html')

    return render_template('register.html')

@app.route('/upload', methods=['GET', 'POST'])
@login_required
@admin_required  # This ensures only admins can access this route
@limiter.limit("10 per hour") if LIMITER_AVAILABLE else lambda x: x
def upload():
    if not current_user.is_admin:
        flash('Only administrators can upload materials', 'danger')
        return redirect(url_for('home'))
        
    if request.method == 'POST':
        try:
            # Check if file is present
            if 'file' not in request.files:
                flash('No file selected', 'danger')
                return redirect(request.url)

            file = request.files['file']
            if file.filename == '':
                flash('No file selected', 'danger')
                return redirect(request.url)

            # Validate file type
            if not allowed_file(file.filename):
                flash('Invalid file type. Allowed types: ' + ', '.join(ALLOWED_EXTENSIONS), 'danger')
                return redirect(request.url)

            # Validate form data
            title = request.form.get('title')
            description = request.form.get('description')
            category = request.form.get('category')
            level = request.form.get('level')
            course_id = request.form.get('course_id')

            if not all([title, description, category, level, course_id]):
                flash('All fields are required', 'danger')
                return redirect(request.url)

            # Generate unique filename
            filename = generate_unique_filename(file.filename)
            
            # Create materials directory if it doesn't exist
            materials_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'materials')
            os.makedirs(materials_dir, exist_ok=True)
            
            # Save the file
            file_path = os.path.join(materials_dir, filename)
            file.save(file_path)

            # Create material record
            material = Material(
                title=title,
                description=description,
                filename=filename,
                category=category,
                level=level,
                course_id=course_id,
                uploaded_by=current_user.id
            )

            db.session.add(material)
            db.session.commit()
            
            flash('Material uploaded successfully', 'success')
            return redirect(url_for('material_detail', material_id=material.id))

        except Exception as e:
            db.session.rollback()
            flash(f'Error uploading file: {str(e)}', 'danger')
            return redirect(request.url)

    # Get courses for the form
    courses = Course.query.order_by(Course.code).all()
    return render_template('upload.html', courses=courses)

@app.route('/profile')
@login_required
def profile():
    user_materials = Material.query.filter_by(uploaded_by=current_user.id).all()
    user_comments = Comment.query.filter_by(user_id=current_user.id).all()
    return render_template('profile.html', user_materials=user_materials, user_comments=user_comments, user=current_user)

@app.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def edit_profile():
    if request.method == 'POST':
        try:
            # Get form data
            bio = request.form.get('bio', '')
            department = request.form.get('department')
            student_id = request.form.get('student_id')

            # Validate required fields
            if not all([department, student_id]):
                flash('Department and Student ID are required fields', 'danger')
                return redirect(url_for('edit_profile'))

            # Update user profile
            current_user.bio = bio
            current_user.department = department
            current_user.student_id = student_id

            # Save changes to database
            db.session.commit()
            flash('Profile updated successfully', 'success')
            return redirect(url_for('profile'))

        except Exception as e:
            db.session.rollback()
            flash('An error occurred while updating your profile', 'danger')
            print(f"Profile update error: {str(e)}")
            return redirect(url_for('edit_profile'))

    return render_template('edit_profile.html')

@app.route('/material/<int:material_id>')
@login_required
def material_detail(material_id):
    material = Material.query.get_or_404(material_id)
    comments = Comment.query.filter_by(material_id=material_id).order_by(Comment.date_posted.desc()).all()
    user_rating = Rating.query.filter_by(material_id=material_id, user_id=current_user.id).first()
    return render_template('material_detail.html', material=material, comments=comments, user_rating=user_rating)

@app.route('/material/<int:material_id>/rate', methods=['POST'])
@login_required
def rate_material(material_id):
    material = Material.query.get_or_404(material_id)
    rating_value = request.form.get('rating', type=int)
    
    if not rating_value or rating_value < 1 or rating_value > 5:
        flash('Invalid rating value', 'error')
        return redirect(url_for('material_detail', material_id=material_id))
    
    existing_rating = Rating.query.filter_by(material_id=material_id, user_id=current_user.id).first()
    
    if existing_rating:
        existing_rating.value = rating_value
    else:
        new_rating = Rating(
            value=rating_value,
            material_id=material_id,
            user_id=current_user.id
        )
        db.session.add(new_rating)
    
    db.session.commit()
    flash('Rating submitted successfully', 'success')
    return redirect(url_for('material_detail', material_id=material_id))

@app.route('/material/<int:material_id>/comment', methods=['POST'])
@login_required
def add_comment(material_id):
    material = Material.query.get_or_404(material_id)
    content = request.form.get('content')
    
    if not content:
        flash('Comment cannot be empty', 'error')
        return redirect(url_for('material_detail', material_id=material_id))
    
    new_comment = Comment(
        content=content,
        material_id=material_id,
        user_id=current_user.id
    )
    
    db.session.add(new_comment)
    db.session.commit()
    
    flash('Comment added successfully', 'success')
    return redirect(url_for('material_detail', material_id=material_id))

@app.route('/material/<int:material_id>/download')
@login_required
def download_material(material_id):
    material = Material.query.get_or_404(material_id)
    try:
        return send_from_directory(
            os.path.join(app.config['UPLOAD_FOLDER'], 'materials'),
            material.filename,
            as_attachment=True
        )
    except Exception as e:
        flash('Error downloading file', 'error')
        return redirect(url_for('material_detail', material_id=material_id))

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out', 'info')
    return redirect(url_for('landing'))

# Admin Routes
@app.route('/admin')
@login_required
def admin():
    if not current_user.is_admin:
        flash('Access denied', 'error')
        return redirect(url_for('home'))
    
    users = User.query.all()
    materials = Material.query.all()
    courses = Course.query.all()
    
    # Statistics
    total_users = User.query.count()
    total_materials = Material.query.count()
    total_downloads = db.session.query(func.sum(Material.downloads)).scalar() or 0
    total_comments = Comment.query.count()
    
    return render_template('admin.html', 
                         users=users, 
                         materials=materials, 
                         courses=courses,
                         total_users=total_users,
                         total_materials=total_materials,
                         total_downloads=total_downloads,
                         total_comments=total_comments)

@app.route('/admin/toggle_admin/<int:user_id>', methods=['POST'])
@login_required
def toggle_admin(user_id):
    user = User.query.get_or_404(user_id)
    user.is_admin = not user.is_admin
    db.session.commit()
    flash(f'Admin status updated for {user.username}')
    return redirect(url_for('admin'))

@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
@login_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('Cannot delete your own account')
        return redirect(url_for('admin'))
    
    # Delete user's materials
    Material.query.filter_by(uploaded_by=user.id).delete()
    db.session.delete(user)
    db.session.commit()
    flash(f'User {user.username} deleted')
    return redirect(url_for('admin'))

@app.route('/admin/delete_material/<int:material_id>', methods=['POST'])
@login_required
def delete_material(material_id):
    material = Material.query.get_or_404(material_id)
    filename = material.filename
    
    # Delete file from filesystem
    try:
        os.remove(os.path.join(app.config['UPLOAD_FOLDER'], 'materials', filename))
    except:
        pass
    
    db.session.delete(material)
    db.session.commit()
    flash('Material deleted')
    return redirect(url_for('admin'))

@app.route('/admin/courses')
@login_required
@admin_required
def admin_courses():
    courses = Course.query.order_by(Course.code).all()
    return render_template('admin/courses.html', courses=courses)

@app.route('/admin/courses/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_course():
    if request.method == 'POST':
        code = request.form.get('code')
        name = request.form.get('name')
        description = request.form.get('description')
        level = request.form.get('level')
        department = request.form.get('department')
        
        if not all([code, name, level, department]):
            flash('All fields are required', 'error')
            return redirect(url_for('add_course'))
        
        if Course.query.filter_by(code=code).first():
            flash('Course code already exists', 'error')
            return redirect(url_for('add_course'))
        
        course = Course(
            code=code,
            name=name,
            description=description,
            level=level,
            department=department
        )
        
        db.session.add(course)
        db.session.commit()
        
        flash('Course added successfully', 'success')
        return redirect(url_for('admin_courses'))
    
    return render_template('admin/add_course.html')

@app.route('/admin/courses/<int:course_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_course(course_id):
    course = Course.query.get_or_404(course_id)
    
    if request.method == 'POST':
        code = request.form.get('code')
        name = request.form.get('name')
        description = request.form.get('description')
        level = request.form.get('level')
        department = request.form.get('department')
        
        if not all([code, name, level, department]):
            flash('All fields are required', 'error')
            return redirect(url_for('edit_course', course_id=course_id))
        
        existing_course = Course.query.filter_by(code=code).first()
        if existing_course and existing_course.id != course_id:
            flash('Course code already exists', 'error')
            return redirect(url_for('edit_course', course_id=course_id))
        
        course.code = code
        course.name = name
        course.description = description
        course.level = level
        course.department = department
        
        db.session.commit()
        
        flash('Course updated successfully', 'success')
        return redirect(url_for('admin_courses'))
    
    return render_template('admin/edit_course.html', course=course)

@app.route('/admin/courses/<int:course_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_course(course_id):
    course = Course.query.get_or_404(course_id)
    
    if course.materials:
        flash('Cannot delete course with associated materials', 'error')
        return redirect(url_for('admin_courses'))
    
    db.session.delete(course)
    db.session.commit()
    
    flash('Course deleted successfully', 'success')
    return redirect(url_for('admin_courses'))

@app.route('/verify-email/<token>')
def verify_email(token):
    user = User.query.filter_by(verification_token=token).first()
    if user and user.verification_token_expiry > datetime.utcnow():
        user.is_verified = True
        user.verification_token = None
        user.verification_token_expiry = None
        db.session.commit()
        flash('Your email has been verified!', 'success')
    else:
        flash('The verification link is invalid or has expired.', 'error')
    return redirect(url_for('login'))

@app.route('/reset-password-request', methods=['GET', 'POST'])
@limiter.limit("3 per hour") if LIMITER_AVAILABLE else lambda x: x
def reset_password_request():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        user = User.query.filter_by(email=email).first()
        if user:
            send_password_reset_email(user)
        flash('If an account exists with that email, you will receive password reset instructions.', 'info')
        return redirect(url_for('login'))
    
    return render_template('reset_password_request.html')

@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    
    user = User.query.filter_by(reset_token=token).first()
    if not user or user.reset_token_expiry < datetime.utcnow():
        flash('The password reset link is invalid or has expired.', 'error')
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return redirect(url_for('reset_password', token=token))
        
        is_valid, message = validate_password(password)
        if not is_valid:
            flash(message, 'error')
            return redirect(url_for('reset_password', token=token))
        
        user.set_password(password)
        user.reset_token = None
        user.reset_token_expiry = None
        db.session.commit()
        flash('Your password has been reset!', 'success')
        return redirect(url_for('login'))
    
    return render_template('reset_password.html')

@app.route('/test-email')
def test_email():
    try:
        msg = Message('Test Email from NeuraLib',
                      recipients=[app.config['MAIL_USERNAME']])
        msg.body = 'This is a test email to verify the email configuration is working correctly.'
        mail.send(msg)
        flash('Test email sent successfully!', 'success')
    except Exception as e:
        flash(f'Error sending test email: {str(e)}', 'error')
    return redirect(url_for('landing'))

@app.route('/debug-email-config')
def debug_email_config():
    config = {
        'MAIL_SERVER': app.config['MAIL_SERVER'],
        'MAIL_PORT': app.config['MAIL_PORT'],
        'MAIL_USE_TLS': app.config['MAIL_USE_TLS'],
        'MAIL_USERNAME': app.config['MAIL_USERNAME'],
        'MAIL_DEFAULT_SENDER': app.config['MAIL_DEFAULT_SENDER'],
        'MAIL_PASSWORD': '***' if app.config['MAIL_PASSWORD'] else None
    }
    return jsonify(config)

def create_sample_courses():
    sample_courses = [
        {
            'code': 'CSC101',
            'name': 'Introduction to Computer Science',
            'description': 'Basic concepts of computer science and programming',
            'department': 'Computer Science',
            'level': '100'
        },
        {
            'code': 'CSC201',
            'name': 'Data Structures and Algorithms',
            'description': 'Study of fundamental data structures and algorithms',
            'department': 'Computer Science',
            'level': '200'
        },
        {
            'code': 'CSC301',
            'name': 'Database Systems',
            'description': 'Design and implementation of database systems',
            'department': 'Computer Science',
            'level': '300'
        },
        {
            'code': 'CSC401',
            'name': 'Software Engineering',
            'description': 'Principles and practices of software development',
            'department': 'Computer Science',
            'level': '400'
        },
        {
            'code': 'MAT101',
            'name': 'Introduction to Mathematics',
            'description': 'Basic mathematical concepts and problem-solving',
            'department': 'Mathematics',
            'level': '100'
        },
        {
            'code': 'PHY101',
            'name': 'Introduction to Physics',
            'description': 'Basic principles of physics and mechanics',
            'department': 'Physics',
            'level': '100'
        }
    ]
    
    for course_data in sample_courses:
        if not Course.query.filter_by(code=course_data['code']).first():
            course = Course(**course_data)
            db.session.add(course)
    
    try:
        db.session.commit()
        print("Sample courses created successfully!")
    except Exception as e:
        db.session.rollback()
        print(f"Error creating sample courses: {str(e)}")

def create_sample_materials():
    # Get the admin user
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        return
    
    # Get all courses
    courses = Course.query.all()
    if not courses:
        return

    sample_materials = [
        {
            'title': 'Introduction to Python Programming',
            'description': 'A comprehensive guide to Python programming basics',
            'category': 'course_outline',
            'level': '100',
            'course_id': next(c.id for c in courses if c.code == 'CSC101'),
            'uploaded_by': admin.id,
            'filename': 'sample.pdf'  # This is just a placeholder
        },
        {
            'title': 'Data Structures Implementation Guide',
            'description': 'Detailed implementation of common data structures',
            'category': 'manual',
            'level': '200',
            'course_id': next(c.id for c in courses if c.code == 'CSC201'),
            'uploaded_by': admin.id,
            'filename': 'sample.pdf'
        },
        {
            'title': 'Database Design Patterns',
            'description': 'Common database design patterns and best practices',
            'category': 'pdf',
            'level': '300',
            'course_id': next(c.id for c in courses if c.code == 'CSC301'),
            'uploaded_by': admin.id,
            'filename': 'sample.pdf'
        },
        {
            'title': 'Software Development Lifecycle',
            'description': 'Comprehensive guide to SDLC methodologies',
            'category': 'course_outline',
            'level': '400',
            'course_id': next(c.id for c in courses if c.code == 'CSC401'),
            'uploaded_by': admin.id,
            'filename': 'sample.pdf'
        }
    ]
    
    for material_data in sample_materials:
        if not Material.query.filter_by(title=material_data['title']).first():
            material = Material(**material_data)
            db.session.add(material)
    
    try:
        db.session.commit()
        print("Sample materials created successfully!")
    except Exception as e:
        db.session.rollback()
        print(f"Error creating sample materials: {str(e)}")

def create_sample_ratings():
    # Get the admin user
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        return
    
    # Get all materials
    materials = Material.query.all()
    if not materials:
        return

    # Create some sample ratings
    sample_ratings = [
        {'material_id': materials[0].id, 'user_id': admin.id, 'value': 5},
        {'material_id': materials[0].id, 'user_id': admin.id, 'value': 4},
        {'material_id': materials[1].id, 'user_id': admin.id, 'value': 5},
        {'material_id': materials[2].id, 'user_id': admin.id, 'value': 3},
        {'material_id': materials[3].id, 'user_id': admin.id, 'value': 4}
    ]
    
    for rating_data in sample_ratings:
        if not Rating.query.filter_by(
            material_id=rating_data['material_id'],
            user_id=rating_data['user_id']
        ).first():
            rating = Rating(**rating_data)
            db.session.add(rating)
    
    try:
        db.session.commit()
        print("Sample ratings created successfully!")
    except Exception as e:
        db.session.rollback()
        print(f"Error creating sample ratings: {str(e)}")

# Create all database tables
with app.app_context():
    # Create tables if they don't exist
    db.create_all()
    
    # Create admin user if not exists
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        admin = User(
            username='admin',
            email='admin@fuoye.edu.ng',
            is_admin=True,
            is_verified=True,
            department='Administration',
            student_id='ADMIN001'
        )
        admin.set_password('admin@fuoye')  # Updated admin password
        db.session.add(admin)
        db.session.commit()
    
    # Create sample data only if no courses exist
    if Course.query.count() == 0:
        create_sample_courses()
        create_sample_materials()
        create_sample_ratings()

# Add error handlers
@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify(error="Rate limit exceeded"), 429

@app.errorhandler(413)
def request_entity_too_large(error):
    return jsonify(error="File too large"), 413

@app.errorhandler(400)
def bad_request(error):
    return jsonify(error="Bad request"), 400

@app.errorhandler(404)
def not_found(error):
    return jsonify(error="Not found"), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return jsonify(error="Internal server error"), 500

if __name__ == "__main__":
    from waitress import serve
    serve(app, host="0.0.0.0", port=8000)