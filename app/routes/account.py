from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from ..auth import ROLE_LABELS, can_preview_roles, detect_windows_username
from ..db import get_db

bp = Blueprint("account", __name__, url_prefix="/account")


@bp.route("/switch", methods=["GET", "POST"])
def switch():
    db = get_db()
    if request.method == "POST":
        choice = request.form.get("user_id", "auto")
        if choice == "auto":
            session.pop("override_user_id", None)
        else:
            session["override_user_id"] = int(choice)
        return redirect(url_for("overview.index"))

    users = db.execute("SELECT * FROM users ORDER BY display_name").fetchall()
    detected = detect_windows_username()
    return render_template("switch_user.html", users=users, detected=detected, roles=ROLE_LABELS)


@bp.route("/preview", methods=["GET", "POST"])
def preview():
    if not can_preview_roles():
        flash("Role preview is only available to the designated test account.", "error")
        return redirect(url_for("overview.index"))

    if request.method == "POST":
        role = request.form.get("role", "off")
        if role == "off":
            session.pop("preview_role", None)
        elif role in ROLE_LABELS:
            session["preview_role"] = role
        return redirect(url_for("overview.index"))

    return render_template(
        "preview_role.html", roles=ROLE_LABELS, current_preview=session.get("preview_role")
    )
