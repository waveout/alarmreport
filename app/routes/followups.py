from flask import Blueprint, redirect, render_template, request, url_for

from ..db import get_db
from ..timeutils import now_central_str

bp = Blueprint("followups", __name__, url_prefix="/followups")


@bp.route("/", methods=["GET", "POST"])
def index():
    db = get_db()
    if request.method == "POST":
        alarm_id = request.form.get("alarm_id") or None
        assignee = request.form.get("assignee", "").strip()
        due_date = request.form.get("due_date") or None
        notes = request.form.get("notes", "").strip()
        timestamp = now_central_str()
        db.execute(
            "INSERT INTO follow_ups (alarm_id, assignee, status, due_date, notes, created_at, updated_at) "
            "VALUES (?, ?, 'open', ?, ?, ?, ?)",
            (alarm_id, assignee, due_date, notes, timestamp, timestamp),
        )
        db.commit()
        return redirect(url_for("followups.index"))

    followups = db.execute(
        """
        SELECT f.*, a.description, a.alarm_desc, a.alarm_date
        FROM follow_ups f LEFT JOIN alarms a ON a.id = f.alarm_id
        ORDER BY f.created_at DESC LIMIT 100
        """
    ).fetchall()
    recent_alarms = db.execute(
        "SELECT id, alarm_date, description, alarm_desc FROM alarms ORDER BY alarm_date DESC LIMIT 50"
    ).fetchall()
    return render_template("followups.html", followups=followups, recent_alarms=recent_alarms)


@bp.route("/<int:followup_id>/close", methods=["POST"])
def close(followup_id):
    db = get_db()
    db.execute(
        "UPDATE follow_ups SET status = 'closed', updated_at = ? WHERE id = ?",
        (now_central_str(), followup_id),
    )
    db.commit()
    return redirect(url_for("followups.index"))
