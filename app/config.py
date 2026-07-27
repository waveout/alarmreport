import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Config:
    BASE_DIR = BASE_DIR
    DATA_DIR = os.path.join(BASE_DIR, "data")
    DB_PATH = os.path.join(DATA_DIR, "alarms.db")

    DEFAULT_INCOMING_DIR = os.path.join(DATA_DIR, "incoming")
    DEFAULT_BACKUP_DIR = os.path.join(DATA_DIR, "backup")
    DEFAULT_REPORTS_DIR = os.path.join(DATA_DIR, "reports")
    DEFAULT_WATCH_INTERVAL_SECONDS = 30

    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")
