"""
One-time migration: brings an existing neuralib.db (created by the old
run.py schema) in line with the schema now defined in models.py.

Safe to run multiple times - it checks what's already there before
changing anything, and it doesn't drop or rewrite any existing rows.

Usage:
    python migrate_db.py
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'neuralib.db')


def column_exists(cur, table, column):
    cur.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cur.fetchall())


def main():
    if not os.path.exists(DB_PATH):
        print(f"No database found at {DB_PATH} - nothing to migrate. "
              f"A fresh one will be created with the correct schema on first run.")
        return

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    changed = False

    if not column_exists(cur, 'user', 'created_at'):
        cur.execute("ALTER TABLE user ADD COLUMN created_at DATETIME")
        print("Added user.created_at")
        changed = True

    if not column_exists(cur, 'user', 'last_login'):
        cur.execute("ALTER TABLE user ADD COLUMN last_login DATETIME")
        print("Added user.last_login")
        changed = True

    if column_exists(cur, 'material', 'uploaded_by') and not column_exists(cur, 'material', 'user_id'):
        cur.execute("ALTER TABLE material RENAME COLUMN uploaded_by TO user_id")
        print("Renamed material.uploaded_by -> material.user_id")
        changed = True

    if not column_exists(cur, 'rating', 'date_posted'):
        cur.execute("ALTER TABLE rating ADD COLUMN date_posted DATETIME")
        print("Added rating.date_posted")
        changed = True

    if not column_exists(cur, 'user', 'last_seen'):
        cur.execute("ALTER TABLE user ADD COLUMN last_seen DATETIME")
        print("Added user.last_seen")
        changed = True

    if changed:
        con.commit()
        print("Migration complete.")
    else:
        print("Database already matches models.py - nothing to do.")

    con.close()


if __name__ == "__main__":
    main()
