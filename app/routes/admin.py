import os
import sqlite3

from flask import Blueprint, flash, redirect, render_template, request, url_for

from ..auth import ROLE_LABELS, VALID_ROLES
from ..db import get_db, get_setting, set_setting
from ..timeutils import now_central_str

bp = Blueprint("admin", __name__, url_prefix="/admin")

SETTINGS_KEYS = ["incoming_dir", "backup_dir", "watch_interval_seconds"]


@bp.route("/", methods=["GET", "POST"])
def index():
    db = get_db()
    if request.method == "POST":
        for key in SETTINGS_KEYS:
            value = request.form.get(key, "").strip()
            if not value:
                continue
            if key == "watch_interval_seconds" and not value.isdigit():
                flash("Watch interval must be a whole number of seconds.", "error")
                continue
            if key in ("incoming_dir", "backup_dir"):
                os.makedirs(value, exist_ok=True)
            set_setting(db, key, value)
        flash("Settings saved.", "success")
        return redirect(url_for("admin.index"))

    settings = {key: get_setting(db, key) for key in SETTINGS_KEYS}
    users = db.execute("SELECT * FROM users ORDER BY display_name").fetchall()
    return render_template("administration.html", settings=settings, users=users, roles=ROLE_LABELS)


@bp.route("/users", methods=["POST"])
def create_user():
    db = get_db()
    windows_username = request.form.get("windows_username", "").strip()
    display_name = request.form.get("display_name", "").strip()
    role = request.form.get("role", "viewer")

    if not windows_username or not display_name or role not in VALID_ROLES:
        flash("Please provide a Windows username, display name, and valid role.", "error")
        return redirect(url_for("admin.index"))

    try:
        timestamp = now_central_str()
        db.execute(
            "INSERT INTO users (windows_username, display_name, role, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (windows_username, display_name, role, timestamp, timestamp),
        )
        db.commit()
        flash(f"Added user {display_name}.", "success")
    except sqlite3.IntegrityError:
        flash(f"A user with Windows username '{windows_username}' already exists.", "error")
    return redirect(url_for("admin.index"))


@bp.route("/users/<int:user_id>/update", methods=["POST"])
def update_user(user_id):
    db = get_db()
    display_name = request.form.get("display_name", "").strip()
    role = request.form.get("role", "viewer")

    if not display_name or role not in VALID_ROLES:
        flash("Invalid user update.", "error")
        return redirect(url_for("admin.index"))

    db.execute(
        "UPDATE users SET display_name = ?, role = ?, updated_at = ? WHERE id = ?",
        (display_name, role, now_central_str(), user_id),
    )
    db.commit()
    flash("User updated.", "success")
    return redirect(url_for("admin.index"))


@bp.route("/users/<int:user_id>/delete", methods=["POST"])
def delete_user(user_id):
    db = get_db()
    db.execute("DELETE FROM users WHERE id = ?", (user_id,))
    db.commit()
    flash("User removed.", "success")
    return redirect(url_for("admin.index"))
