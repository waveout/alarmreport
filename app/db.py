import os
import sqlite3

from flask import current_app, g

SCHEMA = """
CREATE TABLE IF NOT EXISTS data_loads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    backup_filename TEXT,
    unit INTEGER,
    loaded_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    row_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'in_progress',
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS alarms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alarm_date TEXT,
    compound TEXT,
    block TEXT,
    description TEXT,
    name TEXT,
    alarm_type TEXT,
    alarm_desc TEXT,
    alm_rtn TEXT,
    priority INTEGER,
    value TEXT,
    alarm_value TEXT,
    units TEXT,
    location TEXT,
    grp TEXT,
    unit INTEGER,
    data_load_id INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (data_load_id) REFERENCES data_loads(id)
);
CREATE INDEX IF NOT EXISTS idx_alarms_date ON alarms(alarm_date);
CREATE INDEX IF NOT EXISTS idx_alarms_priority ON alarms(priority);
CREATE INDEX IF NOT EXISTS idx_alarms_description ON alarms(description);
CREATE INDEX IF NOT EXISTS idx_alarms_unit ON alarms(unit);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    windows_username TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'viewer',
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS signoffs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_date TEXT NOT NULL,
    user_name TEXT NOT NULL,
    windows_username TEXT,
    acknowledged INTEGER NOT NULL DEFAULT 0,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS follow_ups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alarm_id INTEGER,
    assignee TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    due_date TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (alarm_id) REFERENCES alarms(id)
);

CREATE TABLE IF NOT EXISTS draft_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS generated_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    date_from TEXT,
    date_to TEXT,
    priority_filter TEXT,
    unit_filter TEXT,
    row_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


def get_connection(db_path):
    """Create a standalone connection for use outside of a Flask request context
    (e.g. the background CSV importer thread). Caller is responsible for closing it."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = get_connection(db_path)
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)
        conn.commit()
        _migrate_schema(conn)
        conn.commit()
    finally:
        conn.close()


def _migrate_schema(conn):
    """Add columns to tables that pre-date them, for DBs created before a schema change.
    CREATE TABLE IF NOT EXISTS won't add new columns to an already-existing table."""
    migrations = {
        "alarms": [("unit", "INTEGER")],
        "data_loads": [("unit", "INTEGER")],
        "generated_reports": [("unit_filter", "TEXT")],
    }
    for table, columns in migrations.items():
        existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        for column_name, column_type in columns:
            if column_name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column_name} {column_type}")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_alarms_unit ON alarms(unit)")
    _migrate_user_roles(conn)


def _migrate_user_roles(conn):
    """Older DBs have a CHECK(role IN ('bto','viewer')) constraint on users, which blocks
    newer roles (team_leader, manager). SQLite can't alter a CHECK constraint in place,
    so rebuild the table without it if the old constraint is still present."""
    row = conn.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'users'").fetchone()
    if row and row["sql"] and "CHECK" in row["sql"]:
        conn.execute("ALTER TABLE users RENAME TO users_old")
        conn.execute(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                windows_username TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'viewer',
                created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            )
            """
        )
        conn.execute(
            "INSERT INTO users (id, windows_username, display_name, role, created_at, updated_at) "
            "SELECT id, windows_username, display_name, role, created_at, updated_at FROM users_old"
        )
        conn.execute("DROP TABLE users_old")


def seed_default_settings(db_path, defaults):
    conn = get_connection(db_path)
    try:
        for key, value in defaults.items():
            conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value))
        conn.commit()
    finally:
        conn.close()


def get_setting(conn, key, default=None):
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row is not None else default


def set_setting(conn, key, value):
    conn.execute(
        """
        INSERT INTO settings (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )
    conn.commit()


def get_db():
    """Return a request-scoped connection, cached on flask.g."""
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DB_PATH"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_app(app):
    app.teardown_appcontext(close_db)
