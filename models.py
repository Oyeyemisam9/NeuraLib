from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    last_seen = db.Column(db.DateTime)
    profile_picture = db.Column(db.String(200))
    department = db.Column(db.String(100))
    student_id = db.Column(db.String(20), unique=True)
    bio = db.Column(db.Text)
    
    # Email verification fields
    is_verified = db.Column(db.Boolean, default=False)
    verification_token = db.Column(db.String(128))
    verification_token_expiry = db.Column(db.DateTime)
    
    # Password reset fields
    reset_token = db.Column(db.String(128))
    reset_token_expiry = db.Column(db.DateTime)

    # Note: materials/comments/ratings back-references are created by the
    # backref= on Material.uploader, Comment.user, and Rating.user below.
    # Declaring them again here caused a duplicate-relationship crash
    # (SQLAlchemy: "Error creating backref ... property of that name
    # exists"), so they've been removed from this side.

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username}>'

class Material(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    level = db.Column(db.String(20), nullable=False)
    upload_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    downloads = db.Column(db.Integer, default=0)
    
    # Foreign Keys
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    
    # Relationships
    uploader = db.relationship('User', backref=db.backref('materials', lazy=True))
    course = db.relationship('Course', backref=db.backref('materials', lazy=True))
    
    @property
    def average_rating(self):
        ratings = [rating.value for rating in self.ratings]
        return sum(ratings) / len(ratings) if ratings else 0
    
    def __repr__(self):
        return f'Material({self.title}, {self.category}, {self.level})'

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    date_posted = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    # Foreign Keys
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    material_id = db.Column(db.Integer, db.ForeignKey('material.id'), nullable=False)
    
    # Relationships
    # Named 'author' (not 'user') because templates/material_detail.html
    # reads comment.author.username.
    author = db.relationship('User', backref=db.backref('comments', lazy=True))
    material = db.relationship('Material', backref=db.backref('comments', lazy=True))
    
    def __repr__(self):
        return f'Comment({self.author.username}, {self.material.title})'

class Rating(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    value = db.Column(db.Integer, nullable=False)
    date_posted = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    # Foreign Keys
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    material_id = db.Column(db.Integer, db.ForeignKey('material.id'), nullable=False)
    
    # Relationships
    user = db.relationship('User', backref=db.backref('ratings', lazy=True))
    material = db.relationship('Material', backref=db.backref('ratings', lazy=True))
    
    def __repr__(self):
        return f'Rating({self.value}, {self.user.username}, {self.material.title})'

class HelpDeskMessage(db.Model):
    """
    A single message in a student's Help Desk thread. Every message in a
    thread shares the same student_id (the student who owns the thread) -
    sender_id tells you whether that particular message was written by
    the student or by whichever admin replied.
    """
    id = db.Column(db.Integer, primary_key=True)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    is_read_by_admin = db.Column(db.Boolean, default=False)
    is_read_by_student = db.Column(db.Boolean, default=False)

    # Foreign Keys
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    # Relationships
    student = db.relationship('User', foreign_keys=[student_id], backref=db.backref('helpdesk_thread_messages', lazy=True))
    sender = db.relationship('User', foreign_keys=[sender_id])

    def __repr__(self):
        return f'HelpDeskMessage(student={self.student_id}, sender={self.sender_id})'

class Download(db.Model):
    """
    Tracks which materials a student has downloaded or opened, so the
    'My Downloads' offline section knows what to show them. One row per
    (user, material) pair - re-downloading just bumps downloaded_at rather
    than creating duplicates.
    """
    id = db.Column(db.Integer, primary_key=True)
    downloaded_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    material_id = db.Column(db.Integer, db.ForeignKey('material.id'), nullable=False)

    user = db.relationship('User', backref=db.backref('saved_downloads', lazy=True))
    material = db.relationship('Material', backref=db.backref('downloaded_by', lazy=True))

    __table_args__ = (db.UniqueConstraint('user_id', 'material_id', name='uq_user_material_download'),)

class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), nullable=False, unique=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    level = db.Column(db.String(20), nullable=False)  # 100, 200, 300, 400
    department = db.Column(db.String(100), nullable=False)
    
    def __repr__(self):
        return f'Course({self.code}, {self.name})'

class QuizCategory(db.Model):
    """A subject area students can pick, e.g. 'General Knowledge', 'Science'."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text)

    questions = db.relationship('QuizQuestion', backref='category', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'QuizCategory({self.name})'

class QuizQuestion(db.Model):
    """A single multiple-choice question within a category."""
    id = db.Column(db.Integer, primary_key=True)
    question_text = db.Column(db.Text, nullable=False)
    option_a = db.Column(db.String(255), nullable=False)
    option_b = db.Column(db.String(255), nullable=False)
    option_c = db.Column(db.String(255), nullable=False)
    option_d = db.Column(db.String(255), nullable=False)
    correct_option = db.Column(db.String(1), nullable=False)  # 'a', 'b', 'c', or 'd'
    explanation = db.Column(db.Text)  # optional, shown after answering

    category_id = db.Column(db.Integer, db.ForeignKey('quiz_category.id'), nullable=False)

    def __repr__(self):
        return f'QuizQuestion({self.question_text[:40]!r})'

class QuizAttempt(db.Model):
    """A record of one completed quiz - used for a student's quiz history."""
    id = db.Column(db.Integer, primary_key=True)
    score = db.Column(db.Integer, nullable=False)
    total_questions = db.Column(db.Integer, nullable=False)
    taken_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('quiz_category.id'), nullable=False)

    user = db.relationship('User', backref=db.backref('quiz_attempts', lazy=True))
    category = db.relationship('QuizCategory')

    def __repr__(self):
        return f'QuizAttempt(user={self.user_id}, score={self.score}/{self.total_questions})' 