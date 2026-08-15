"""
One-time cleanup: removes the placeholder demo materials that used to be
auto-seeded on first run (they all have filename == 'sample.pdf', which no
real upload ever produces - real uploads get a generated UUID filename).
Any material you've actually uploaded is left untouched.

Safe to run multiple times - if there's nothing left matching that
pattern, it just says so and exits.

Usage:
    python cleanup_seed_data.py
"""
import os
from app import app
from models import db, Material, Rating, Comment

with app.app_context():
    fake_materials = Material.query.filter_by(filename='sample.pdf').all()

    if not fake_materials:
        print("No seeded demo materials found - nothing to clean up.")
    else:
        for material in fake_materials:
            Rating.query.filter_by(material_id=material.id).delete()
            Comment.query.filter_by(material_id=material.id).delete()
            print(f"Removing: {material.title!r}")
            db.session.delete(material)

        db.session.commit()
        print(f"Removed {len(fake_materials)} seeded demo material(s) and their ratings/comments.")
