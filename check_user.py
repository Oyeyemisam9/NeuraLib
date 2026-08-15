"""
Diagnostic: checks a user's account state directly in the database -
whether they're verified, whether a password reset is still pending, and
whether a candidate password actually matches what's stored.

Usage:
    python check_user.py
"""
from app import app
from models import db, User

username = input("Username to check: ").strip()

with app.app_context():
    user = User.query.filter_by(username=username).first()
    if not user:
        print(f"No user with username '{username}' found.")
    else:
        print(f"\nUsername:        {user.username}")
        print(f"Email:           {user.email}")
        print(f"is_verified:     {user.is_verified}")
        print(f"has reset_token: {bool(user.reset_token)}")
        if user.reset_token:
            print(f"reset_token_expiry: {user.reset_token_expiry}")

        candidate = input("\nEnter a password to test against what's stored (blank to skip): ").strip()
        if candidate:
            print("Password matches:", user.check_password(candidate))
