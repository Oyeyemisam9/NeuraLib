from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, abort, jsonify
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
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
import random
import json
import threading
from flask_wtf.csrf import CSRFProtect
from dotenv import load_dotenv

# Load variables from a local .env file (if one exists) into the environment.
# This must happen before importing storage (which reads STORAGE_* env vars
# at import time) or calling any os.environ.get() below for SECRET_KEY,
# MAIL_USERNAME, MAIL_PASSWORD, etc.
load_dotenv()

from models import db, User, Course, Material, Comment, Rating, HelpDeskMessage, Download, QuizCategory, QuizQuestion, QuizAttempt
import storage

# Try to import Flask-Limiter, but make it optional
try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
    LIMITER_AVAILABLE = True
except ImportError:
    LIMITER_AVAILABLE = False
    print("Warning: Flask-Limiter not installed. Rate limiting will be disabled.")

# Base directory of this file - used to build absolute paths so the app
# behaves the same no matter what directory it's launched from.
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-here')

_database_url = os.environ.get('DATABASE_URL', 'sqlite:///' + os.path.join(BASE_DIR, 'neuralib.db'))
# Render/Heroku-style Postgres URLs use the old "postgres://" scheme, which
# newer SQLAlchemy versions reject - they require "postgresql://" instead.
if _database_url.startswith('postgres://'):
    _database_url = _database_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = _database_url

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(BASE_DIR, 'uploads')
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
# storage_uri defaults to in-memory so the app runs out of the box with no
# extra infrastructure. Set REDIS_URL in the environment to use Redis
# instead (recommended for production with more than one worker process,
# since in-memory limits aren't shared across processes).
if LIMITER_AVAILABLE:
    limiter = Limiter(
        app=app,
        key_func=get_remote_address,
        # This is a global fallback for any route without its own specific
        # limit below - kept generous since normal browsing (especially
        # several people sharing one IP, common on mobile networks) can add
        # up fast. The routes that actually need tight protection (login,
        # register, password reset, upload) have their own stricter limits.
        default_limits=["2000 per day", "500 per hour"],
        storage_uri=os.environ.get('REDIS_URL', 'memory://')
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
# (db comes from models.py so the schema is defined in exactly one place)
login_manager = LoginManager()
mail = Mail()

# Initialize the app with the extensions
db.init_app(app)
login_manager.init_app(app)
mail.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'info'

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

# How recently a user must have been seen to count as "online now" on the
# admin dashboard.
ONLINE_THRESHOLD = timedelta(minutes=5)

@app.before_request
def update_last_seen():
    if current_user.is_authenticated:
        current_user.last_seen = datetime.utcnow()
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()

@app.context_processor
def inject_helpdesk_unread():
    if not current_user.is_authenticated:
        return dict(helpdesk_unread_count=0)

    if current_user.is_admin:
        count = HelpDeskMessage.query.filter(
            HelpDeskMessage.is_read_by_admin == False,
            HelpDeskMessage.sender_id == HelpDeskMessage.student_id
        ).count()
    else:
        count = HelpDeskMessage.query.filter(
            HelpDeskMessage.student_id == current_user.id,
            HelpDeskMessage.is_read_by_student == False,
            HelpDeskMessage.sender_id != current_user.id
        ).count()

    return dict(helpdesk_unread_count=count)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def generate_verification_token():
    return secrets.token_urlsafe(32)

def generate_password_reset_token():
    return secrets.token_urlsafe(32)

def send_async_email(app, msg):
    """Sends an email in a background thread so the request that triggered
    it (e.g. registration) can respond to the browser immediately instead
    of blocking until the SMTP server responds - which can otherwise hang
    a page load for a long time if the mail server is slow."""
    with app.app_context():
        try:
            mail.send(msg)
        except Exception as e:
            print(f"Background email send failed: {str(e)}")

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
    threading.Thread(target=send_async_email, args=(app, msg), daemon=True).start()

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
    threading.Thread(target=send_async_email, args=(app, msg), daemon=True).start()

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

def record_download(user, material):
    """
    Records that this user has downloaded/opened this material, so it shows
    up in their 'My Downloads' offline section. Safe to call repeatedly -
    just bumps the timestamp on repeat downloads instead of duplicating.
    Does not commit; caller is expected to commit.
    """
    existing = Download.query.filter_by(user_id=user.id, material_id=material.id).first()
    if existing:
        existing.downloaded_at = datetime.utcnow()
    else:
        db.session.add(Download(user_id=user.id, material_id=material.id))

# Routes
@app.route('/service-worker.js')
def service_worker():
    # Served from the site root (not /static/) so the browser gives it
    # scope over the whole site by default - a service worker can only
    # control paths at or below the directory it's served from, and it
    # needs to reach /material/... URLs to make offline downloads work.
    response = send_from_directory(app.static_folder, 'service-worker.js')
    response.headers['Content-Type'] = 'application/javascript'
    return response

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
@limiter.limit("20 per minute") if LIMITER_AVAILABLE else lambda x: x
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
                if not user.is_verified:
                    flash('Please verify your email before logging in - check your inbox for the link, '
                          'or use "Resend verification email" below.', 'warning')
                    return render_template('login.html')
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
@limiter.limit("40 per hour") if LIMITER_AVAILABLE else lambda x: x
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

            # Create new user - is_verified starts False; they're activated
            # once they click the link in the verification email.
            user = User(
                username=username,
                email=email,
                student_id=student_id,
                department=department,
                is_verified=False
            )
            user.set_password(password)

            # Add to database
            db.session.add(user)
            db.session.commit()

            try:
                send_verification_email(user)
                flash('Registration successful! Check your email for a verification link before logging in.', 'success')
            except Exception as mail_error:
                print(f"Verification email failed to send: {str(mail_error)}")
                flash('Registration successful, but the verification email could not be sent. '
                      'Contact an admin for help getting verified.', 'warning')

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
            
            # Save the file (Cloudflare R2 if configured, local disk otherwise)
            storage.save_material_file(file, filename, app.config['UPLOAD_FOLDER'])

            # Create material record
            material = Material(
                title=title,
                description=description,
                filename=filename,
                category=category,
                level=level,
                course_id=course_id,
                user_id=current_user.id
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
    user_materials = Material.query.filter_by(user_id=current_user.id).all()
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
        record_download(current_user, material)
        material.downloads = (material.downloads or 0) + 1
        db.session.commit()
        return storage.material_file_response(
            material.filename, app.config['UPLOAD_FOLDER'],
            inline=False, download_name=f"{material.title}.{material.filename.rsplit('.', 1)[-1]}"
        )
    except Exception as e:
        flash('Error downloading file', 'error')
        return redirect(url_for('material_detail', material_id=material_id))

# File types that browsers can actually render natively - anything else
# (doc/docx) can only be offered as a download, not an in-browser preview.
VIEWABLE_EXTENSIONS = {'pdf', 'txt'}

@app.route('/material/<int:material_id>/view')
@login_required
def view_material(material_id):
    material = Material.query.get_or_404(material_id)
    extension = material.filename.rsplit('.', 1)[-1].lower() if '.' in material.filename else ''
    if extension not in VIEWABLE_EXTENSIONS:
        flash('This file type can\'t be previewed in the browser - download it instead.', 'info')
        return redirect(url_for('material_detail', material_id=material_id))

    record_download(current_user, material)
    db.session.commit()
    return storage.material_file_response(material.filename, app.config['UPLOAD_FOLDER'], inline=True)

@app.route('/my-downloads')
@login_required
def my_downloads():
    downloads = Download.query.filter_by(user_id=current_user.id) \
        .order_by(Download.downloaded_at.desc()).all()
    return render_template('my_downloads.html', downloads=downloads, viewable_extensions=VIEWABLE_EXTENSIONS)

# --------------------------------------------------------------------
# Quiz - general knowledge, organized by subject category
# --------------------------------------------------------------------
QUESTIONS_PER_QUIZ = 10

@app.route('/quiz')
@login_required
def quiz_categories():
    categories = QuizCategory.query.all()
    # Question count per category, so the picker can show "12 questions"
    # and grey out categories with nothing in them yet.
    counts = dict(
        db.session.query(QuizQuestion.category_id, func.count(QuizQuestion.id))
        .group_by(QuizQuestion.category_id).all()
    )
    return render_template('quiz_categories.html', categories=categories, counts=counts)

@app.route('/quiz/<int:category_id>')
@login_required
def quiz_take(category_id):
    category = QuizCategory.query.get_or_404(category_id)
    all_questions = QuizQuestion.query.filter_by(category_id=category.id).all()

    if not all_questions:
        flash('This category has no questions yet.', 'info')
        return redirect(url_for('quiz_categories'))

    sample_size = min(QUESTIONS_PER_QUIZ, len(all_questions))
    questions = random.sample(all_questions, sample_size)

    # Options are shuffled per question so the correct answer isn't always
    # in the same position, but we keep the correct letter mapped through
    # so grading still works after shuffling.
    quiz_data = []
    for q in questions:
        options = [
            {'key': 'a', 'text': q.option_a},
            {'key': 'b', 'text': q.option_b},
            {'key': 'c', 'text': q.option_c},
            {'key': 'd', 'text': q.option_d},
        ]
        random.shuffle(options)
        quiz_data.append({
            'id': q.id,
            'question': q.question_text,
            'options': options
        })

    return render_template('quiz_take.html', category=category, quiz_data=quiz_data)

@app.route('/quiz/<int:category_id>/submit', methods=['POST'])
@login_required
def quiz_submit(category_id):
    category = QuizCategory.query.get_or_404(category_id)

    # answers arrives as JSON: {"question_id": "selected_letter", ...}
    try:
        answers = json.loads(request.form.get('answers', '{}'))
    except ValueError:
        answers = {}

    question_ids = [int(qid) for qid in answers.keys()]
    questions = QuizQuestion.query.filter(QuizQuestion.id.in_(question_ids)).all()
    questions_by_id = {q.id: q for q in questions}

    results = []
    score = 0
    for qid_str, selected in answers.items():
        q = questions_by_id.get(int(qid_str))
        if not q:
            continue
        is_correct = (selected == q.correct_option)
        if is_correct:
            score += 1
        results.append({
            'question': q,
            'selected': selected,
            'is_correct': is_correct
        })

    attempt = QuizAttempt(
        user_id=current_user.id,
        category_id=category.id,
        score=score,
        total_questions=len(results)
    )
    db.session.add(attempt)
    db.session.commit()

    return render_template('quiz_result.html', category=category, results=results,
                          score=score, total=len(results))

@app.route('/quiz/history')
@login_required
def quiz_history():
    attempts = QuizAttempt.query.filter_by(user_id=current_user.id) \
        .order_by(QuizAttempt.taken_at.desc()).all()
    return render_template('quiz_history.html', attempts=attempts)

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
    
    users = User.query.order_by(User.last_seen.is_(None), User.last_seen.desc()).all()
    materials = Material.query.all()
    courses = Course.query.all()
    
    # Statistics
    total_users = User.query.count()
    total_materials = Material.query.count()
    total_downloads = db.session.query(func.sum(Material.downloads)).scalar() or 0
    total_comments = Comment.query.count()

    online_cutoff = datetime.utcnow() - ONLINE_THRESHOLD
    online_count = User.query.filter(User.last_seen != None, User.last_seen >= online_cutoff).count()

    return render_template('admin.html', 
                         users=users, 
                         materials=materials, 
                         courses=courses,
                         total_users=total_users,
                         total_materials=total_materials,
                         total_downloads=total_downloads,
                         total_comments=total_comments,
                         online_cutoff=online_cutoff,
                         online_count=online_count)

@app.route('/admin/toggle_admin/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def toggle_admin(user_id):
    user = User.query.get_or_404(user_id)
    user.is_admin = not user.is_admin
    db.session.commit()
    flash(f'Admin status updated for {user.username}')
    return redirect(url_for('admin'))

@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('Cannot delete your own account')
        return redirect(url_for('admin'))

    # Clean up everything that references this user before deleting them
    Material.query.filter_by(user_id=user.id).delete()
    Comment.query.filter_by(user_id=user.id).delete()
    Rating.query.filter_by(user_id=user.id).delete()
    HelpDeskMessage.query.filter(
        (HelpDeskMessage.student_id == user.id) | (HelpDeskMessage.sender_id == user.id)
    ).delete(synchronize_session=False)

    db.session.delete(user)
    db.session.commit()
    flash(f'User {user.username} deleted')
    return redirect(url_for('admin'))

@app.route('/admin/delete_material/<int:material_id>', methods=['POST'])
@login_required
@admin_required
def delete_material(material_id):
    material = Material.query.get_or_404(material_id)
    filename = material.filename
    
    # Delete the actual file (R2 or local disk, whichever is active)
    storage.delete_material_file(filename, app.config['UPLOAD_FOLDER'])

    # Clean up everything that references this material before deleting it
    Comment.query.filter_by(material_id=material.id).delete()
    Rating.query.filter_by(material_id=material.id).delete()
    Download.query.filter_by(material_id=material.id).delete()
    
    db.session.delete(material)
    db.session.commit()
    flash('Material deleted')
    return redirect(url_for('admin'))

# --------------------------------------------------------------------
# Help Desk - two-way messaging between a student and admins
# --------------------------------------------------------------------
@app.route('/help-desk', methods=['GET', 'POST'])
@login_required
def help_desk():
    if current_user.is_admin:
        return redirect(url_for('admin_help_desk'))

    if request.method == 'POST':
        body = request.form.get('body', '').strip()
        if body:
            message = HelpDeskMessage(
                body=body,
                student_id=current_user.id,
                sender_id=current_user.id,
                is_read_by_student=True
            )
            db.session.add(message)
            db.session.commit()
        else:
            flash('Message cannot be empty', 'danger')
        return redirect(url_for('help_desk'))

    messages = HelpDeskMessage.query.filter_by(student_id=current_user.id) \
        .order_by(HelpDeskMessage.created_at.asc()).all()

    # Mark any admin replies as read now that the student has opened the thread
    HelpDeskMessage.query.filter(
        HelpDeskMessage.student_id == current_user.id,
        HelpDeskMessage.is_read_by_student == False
    ).update({'is_read_by_student': True})
    db.session.commit()

    return render_template('help_desk.html', messages=messages)

@app.route('/admin/help-desk')
@login_required
@admin_required
def admin_help_desk():
    # One row per student who has ever sent/received a Help Desk message,
    # newest activity first.
    latest_subq = db.session.query(
        HelpDeskMessage.student_id,
        func.max(HelpDeskMessage.created_at).label('latest')
    ).group_by(HelpDeskMessage.student_id).subquery()

    unread_counts = dict(
        db.session.query(HelpDeskMessage.student_id, func.count(HelpDeskMessage.id))
        .filter(
            HelpDeskMessage.is_read_by_admin == False,
            HelpDeskMessage.sender_id == HelpDeskMessage.student_id
        )
        .group_by(HelpDeskMessage.student_id)
        .all()
    )

    rows = db.session.query(User, latest_subq.c.latest) \
        .join(latest_subq, User.id == latest_subq.c.student_id) \
        .order_by(latest_subq.c.latest.desc()).all()

    threads = []
    for student, latest in rows:
        last_message = HelpDeskMessage.query.filter_by(student_id=student.id) \
            .order_by(HelpDeskMessage.created_at.desc()).first()
        threads.append({
            'student': student,
            'latest': latest,
            'unread': unread_counts.get(student.id, 0),
            'last_message': last_message
        })

    return render_template('admin/help_desk_list.html', threads=threads)

@app.route('/admin/help-desk/<int:student_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_help_desk_thread(student_id):
    student = User.query.get_or_404(student_id)

    if request.method == 'POST':
        body = request.form.get('body', '').strip()
        if body:
            message = HelpDeskMessage(
                body=body,
                student_id=student.id,
                sender_id=current_user.id,
                is_read_by_admin=True
            )
            db.session.add(message)
            db.session.commit()
        else:
            flash('Message cannot be empty', 'danger')
        return redirect(url_for('admin_help_desk_thread', student_id=student.id))

    messages = HelpDeskMessage.query.filter_by(student_id=student.id) \
        .order_by(HelpDeskMessage.created_at.asc()).all()

    HelpDeskMessage.query.filter(
        HelpDeskMessage.student_id == student.id,
        HelpDeskMessage.is_read_by_admin == False
    ).update({'is_read_by_admin': True})
    db.session.commit()

    return render_template('admin/help_desk_thread.html', student=student, messages=messages)

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

# --------------------------------------------------------------------
# Admin: Quiz management
# --------------------------------------------------------------------
@app.route('/admin/quiz')
@login_required
@admin_required
def admin_quiz():
    categories = QuizCategory.query.all()
    counts = dict(
        db.session.query(QuizQuestion.category_id, func.count(QuizQuestion.id))
        .group_by(QuizQuestion.category_id).all()
    )
    return render_template('admin/quiz_categories.html', categories=categories, counts=counts)

@app.route('/admin/quiz/categories/add', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_add_quiz_category():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()

        if not name:
            flash('Category name is required', 'danger')
            return redirect(url_for('admin_add_quiz_category'))

        if QuizCategory.query.filter_by(name=name).first():
            flash('A category with that name already exists', 'danger')
            return redirect(url_for('admin_add_quiz_category'))

        category = QuizCategory(name=name, description=description)
        db.session.add(category)
        db.session.commit()
        flash(f'Category "{name}" created', 'success')
        return redirect(url_for('admin_quiz'))

    return render_template('admin/add_quiz_category.html')

@app.route('/admin/quiz/categories/<int:category_id>/delete', methods=['POST'])
@login_required
@admin_required
def admin_delete_quiz_category(category_id):
    category = QuizCategory.query.get_or_404(category_id)
    db.session.delete(category)  # cascades to its questions
    db.session.commit()
    flash(f'Category "{category.name}" and its questions were deleted', 'success')
    return redirect(url_for('admin_quiz'))

@app.route('/admin/quiz/categories/<int:category_id>/questions', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_quiz_questions(category_id):
    category = QuizCategory.query.get_or_404(category_id)

    if request.method == 'POST':
        question_text = request.form.get('question_text', '').strip()
        option_a = request.form.get('option_a', '').strip()
        option_b = request.form.get('option_b', '').strip()
        option_c = request.form.get('option_c', '').strip()
        option_d = request.form.get('option_d', '').strip()
        correct_option = request.form.get('correct_option', '').strip().lower()
        explanation = request.form.get('explanation', '').strip()

        if not all([question_text, option_a, option_b, option_c, option_d, correct_option]):
            flash('Please fill in the question, all four options, and mark the correct one', 'danger')
            return redirect(url_for('admin_quiz_questions', category_id=category.id))

        if correct_option not in ('a', 'b', 'c', 'd'):
            flash('Correct option must be A, B, C, or D', 'danger')
            return redirect(url_for('admin_quiz_questions', category_id=category.id))

        question = QuizQuestion(
            question_text=question_text,
            option_a=option_a, option_b=option_b, option_c=option_c, option_d=option_d,
            correct_option=correct_option,
            explanation=explanation or None,
            category_id=category.id
        )
        db.session.add(question)
        db.session.commit()
        flash('Question added', 'success')
        return redirect(url_for('admin_quiz_questions', category_id=category.id))

    questions = QuizQuestion.query.filter_by(category_id=category.id).all()
    return render_template('admin/quiz_questions.html', category=category, questions=questions)

@app.route('/admin/quiz/questions/<int:question_id>/delete', methods=['POST'])
@login_required
@admin_required
def admin_delete_quiz_question(question_id):
    question = QuizQuestion.query.get_or_404(question_id)
    category_id = question.category_id
    db.session.delete(question)
    db.session.commit()
    flash('Question deleted', 'success')
    return redirect(url_for('admin_quiz_questions', category_id=category_id))

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

@app.route('/resend-verification', methods=['GET', 'POST'])
@limiter.limit("5 per hour") if LIMITER_AVAILABLE else lambda x: x
def resend_verification():
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    if request.method == 'POST':
        email = request.form.get('email')
        user = User.query.filter_by(email=email).first()
        if user and not user.is_verified:
            try:
                send_verification_email(user)
            except Exception as mail_error:
                print(f"Resend verification email failed: {str(mail_error)}")
        # Same message either way, so we don't reveal which emails are registered
        flash('If that email is registered and not yet verified, a new verification link has been sent.', 'info')
        return redirect(url_for('login'))

    return render_template('resend_verification.html')

@app.route('/reset-password-request', methods=['GET', 'POST'])
@limiter.limit("3 per hour") if LIMITER_AVAILABLE else lambda x: x
def reset_password_request():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        user = User.query.filter_by(email=email).first()
        if user:
            try:
                send_password_reset_email(user)
            except Exception as mail_error:
                print(f"Password reset email failed: {str(mail_error)}")
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
    
    return render_template('reset_password.html', token=token)

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

# Create all database tables
with app.app_context():
    # Create tables if they don't exist
    db.create_all()

    # Create the admin account if it doesn't exist yet.
    # All materials and courses beyond this are added through the admin
    # panel - there is no automatic sample/demo data seeded here.
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

# Add error handlers
@app.errorhandler(429)
def ratelimit_handler(e):
    return render_template('error.html', code=429, icon='fa-stopwatch',
                          message="You've made too many requests in a short time. Please wait a bit and try again."), 429

@app.errorhandler(413)
def request_entity_too_large(error):
    return render_template('error.html', code=413, icon='fa-file-circle-exclamation',
                          message="That file is too large. The maximum upload size is 16MB."), 413

@app.errorhandler(400)
def bad_request(error):
    return render_template('error.html', code=400, icon='fa-triangle-exclamation',
                          message="Something about that request wasn't right. Please try again."), 400

@app.errorhandler(403)
def forbidden(error):
    return render_template('error.html', code=403, icon='fa-lock',
                          message="You don't have permission to access that page."), 403

@app.errorhandler(404)
def not_found(error):
    return render_template('error.html', code=404, icon='fa-map-signs',
                          message="That page doesn't exist, or may have been moved."), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('error.html', code=500, icon='fa-server',
                          message="Something went wrong on our end. Please try again in a moment."), 500

if __name__ == "__main__":
    from waitress import serve
    # Render (and most PaaS hosts) assign a dynamic port via the PORT
    # environment variable - falls back to 8000 for local development.
    port = int(os.environ.get('PORT', 8000))
    serve(app, host="0.0.0.0", port=port)