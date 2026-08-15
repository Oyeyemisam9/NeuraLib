"""
Dev utility: manually verifies a user's account (bypassing the email link)
and optionally sets their password to something you choose - useful when
you're testing locally and don't want to chase down an email.

Usage:
    python verify_user.py
"""
from app import app
from models import db, User

username = input("Username to verify: ").strip()

with app.app_context():
    user = User.query.filter_by(username=username).first()
    if not user:
        print(f"No user with username '{username}' found.")
    else:
        user.is_verified = True
        user.verification_token = None
        user.verification_token_expiry = None
        db.session.commit()
        print(f"'{user.username}' is now verified.")

        set_pw = input("Also set a new password now? (leave blank to skip): ").strip()
        if set_pw:
            user.set_password(set_pw)
            db.session.commit()
            print(f"Password for '{user.username}' set to: {set_pw}")
