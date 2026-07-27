from flask import Blueprint, redirect, render_template, request, url_for

from ..db import get_db
from ..timeutils import now_central_str

bp = Blueprint("draft_notes", __name__, url_prefix="/draft-notes")


@bp.route("/", methods=["GET", "POST"])
def index():
    db = get_db()
    if request.method == "POST":
        content = request.form.get("content", "").strip()
        if content:
            timestamp = now_central_str()
            db.execute(
                "INSERT INTO draft_notes (content, created_at, updated_at) VALUES (?, ?, ?)",
                (content, timestamp, timestamp),
            )
            db.commit()
        return redirect(url_for("draft_notes.index"))

    notes = db.execute("SELECT * FROM draft_notes ORDER BY updated_at DESC LIMIT 100").fetchall()
    return render_template("draft_notes.html", notes=notes)


@bp.route("/<int:note_id>/delete", methods=["POST"])
def delete(note_id):
    db = get_db()
    db.execute("DELETE FROM draft_notes WHERE id = ?", (note_id,))
    db.commit()
    return redirect(url_for("draft_notes.index"))
