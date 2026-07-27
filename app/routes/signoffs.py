from flask import Blueprint, flash, redirect, render_template, request, url_for

from ..auth import get_current_user, is_bto
from ..db import get_db
from ..timeutils import now_central_str, today_central_str

bp = Blueprint("signoffs", __name__, url_prefix="/signoffs")


@bp.route("/", methods=["GET", "POST"])
def index():
    db = get_db()
    current_user = get_current_user()
    if request.method == "POST":
        if not is_bto(current_user):
            flash("Only BTOs/Operators can acknowledge alarms.", "error")
            return redirect(url_for("signoffs.index"))
        report_date = request.form.get("report_date") or today_central_str()
        notes = request.form.get("notes", "").strip()
        timestamp = now_central_str()
        db.execute(
            "INSERT INTO signoffs (report_date, user_name, windows_username, acknowledged, notes, "
            "created_at, updated_at) VALUES (?, ?, ?, 1, ?, ?, ?)",
            (report_date, current_user["display_name"], current_user["windows_username"], notes,
             timestamp, timestamp),
        )
        db.commit()
        flash("Signoff recorded.", "success")
        return redirect(url_for("signoffs.index"))

    signoffs = db.execute("SELECT * FROM signoffs ORDER BY created_at DESC LIMIT 100").fetchall()
    return render_template("signoffs.html", signoffs=signoffs, today=today_central_str())
