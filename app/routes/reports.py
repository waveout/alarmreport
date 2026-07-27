import os

import pandas as pd
from flask import Blueprint, current_app, redirect, render_template, request, send_from_directory, url_for

from ..db import get_db
from ..timeutils import filename_timestamp, now_central_str, today_central_str

bp = Blueprint("reports", __name__, url_prefix="/reports")


@bp.route("/generate", methods=["GET", "POST"])
def generate():
    db = get_db()
    if request.method == "POST":
        date_from = request.form.get("date_from") or today_central_str()
        date_to = request.form.get("date_to") or today_central_str()
        priority = request.form.get("priority", "all")
        unit = request.form.get("unit", "all")

        query = (
            "SELECT alarm_date, unit, priority, description, name, alarm_type, alarm_desc, location, grp "
            "FROM alarms WHERE alarm_date >= ? AND alarm_date <= ?"
        )
        params = [f"{date_from} 00:00:00", f"{date_to} 23:59:59"]
        if priority in ("1", "2", "3"):
            query += " AND priority = ?"
            params.append(int(priority))
        if unit in ("1", "2", "3"):
            query += " AND unit = ?"
            params.append(int(unit))
        query += " ORDER BY alarm_date"
        rows = db.execute(query, params).fetchall()

        reports_dir = current_app.config["DEFAULT_REPORTS_DIR"]
        os.makedirs(reports_dir, exist_ok=True)
        unit_suffix = f"_unit{unit}" if unit in ("1", "2", "3") else ""
        filename = f"alarm_report_{date_from}_{date_to}{unit_suffix}_{filename_timestamp()}.xlsx"
        filepath = os.path.join(reports_dir, filename)

        df = pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame(columns=rows[0].keys() if rows else [])
        df.to_excel(filepath, index=False)

        db.execute(
            "INSERT INTO generated_reports (filename, date_from, date_to, priority_filter, unit_filter, "
            "row_count, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (filename, date_from, date_to, priority, unit, len(rows), now_central_str()),
        )
        db.commit()
        return redirect(url_for("reports.index"))

    return render_template("generate_report.html", today=today_central_str())


@bp.route("/")
def index():
    db = get_db()
    reports = db.execute("SELECT * FROM generated_reports ORDER BY created_at DESC LIMIT 100").fetchall()
    return render_template("reports.html", reports=reports)


@bp.route("/download/<path:filename>")
def download(filename):
    reports_dir = current_app.config["DEFAULT_REPORTS_DIR"]
    return send_from_directory(reports_dir, filename, as_attachment=True)
