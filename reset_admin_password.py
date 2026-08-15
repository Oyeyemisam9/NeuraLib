"""
One-off utility: resets the 'admin' user's password directly in the database.
Run it, then delete it (or just leave it - it only does anything if you run it).

Usage:
    python reset_admin_password.py
"""
from app import app
from models import db, User

NEW_PASSWORD = "admin@fuoye"  # <-- edit this to whatever you want, then run the script

with app.app_context():
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        print("No user with username 'admin' found.")
    else:
        admin.set_password(NEW_PASSWORD)
        db.session.commit()
        print(f"Password for '{admin.username}' ({admin.email}) has been reset.")
        print(f"New password: {NEW_PASSWORD}")
