import os
import sqlite3
from pathlib import Path

# Vercel's deployed application directory is not a writable persistent disk.
# Use /tmp there so the app can start; locally, keep the database in the project.
# For persistent production data, configure DATABASE_PATH for a supported hosted DB
# or migrate to a hosted database service.
if os.environ.get("VERCEL"):
    DB_PATH = Path(os.environ.get("DATABASE_PATH", "/tmp/library.db"))
else:
    DB_PATH = Path(os.environ.get(
        "DATABASE_PATH",
        str(Path(__file__).resolve().parent.parent / "library.db")
    ))

DB_PATH.parent.mkdir(parents=True, exist_ok=True)

SCHEMA = """
CREATE TABLE IF NOT EXISTS members (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    name  TEXT NOT NULL,
    email TEXT UNIQUE,
    role  TEXT NOT NULL DEFAULT 'member'      -- member | author | librarian
);
CREATE TABLE IF NOT EXISTS books (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    author      TEXT NOT NULL,
    isbn        TEXT UNIQUE,
    copies      INTEGER NOT NULL DEFAULT 1,
    available   INTEGER NOT NULL DEFAULT 1,
    genre       TEXT NOT NULL DEFAULT 'General',
    description TEXT NOT NULL DEFAULT '',
    format      TEXT NOT NULL DEFAULT 'physical',   -- physical | ebook
    content     TEXT,                               -- e-book text
    status      TEXT NOT NULL DEFAULT 'published',  -- published | pending
    created_by  INTEGER
);
CREATE TABLE IF NOT EXISTS loans (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id     INTEGER NOT NULL REFERENCES books(id),
    member_id   INTEGER NOT NULL REFERENCES members(id),
    issue_date  TEXT NOT NULL,
    due_date    TEXT NOT NULL,
    return_date TEXT,
    fine        REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS ebook_reads (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id INTEGER NOT NULL REFERENCES members(id),
    book_id   INTEGER NOT NULL REFERENCES books(id),
    read_at   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ratings (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id INTEGER NOT NULL REFERENCES members(id),
    book_id   INTEGER NOT NULL REFERENCES books(id),
    rating    INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    UNIQUE (member_id, book_id)
);
"""

# Columns added after the first version, so an older library.db upgrades itself.
MIGRATIONS = {
    "books": [
        ("genre", "TEXT NOT NULL DEFAULT 'General'"),
        ("description", "TEXT NOT NULL DEFAULT ''"),
        ("format", "TEXT NOT NULL DEFAULT 'physical'"),
        ("content", "TEXT"),
        ("status", "TEXT NOT NULL DEFAULT 'published'"),
        ("created_by", "INTEGER"),
    ],
    "members": [("role", "TEXT NOT NULL DEFAULT 'member'")],
}


def _migrate(conn):
    for table, columns in MIGRATIONS.items():
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        for name, definition in columns:
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
    conn.commit()


def get_connection(path=DB_PATH, init=True):
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if init:
        conn.executescript(SCHEMA)
        _migrate(conn)
    return conn
