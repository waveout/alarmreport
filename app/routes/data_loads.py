from ..db import get_db
from flask import Blueprint, render_template

bp = Blueprint("data_loads", __name__, url_prefix="/data-loads")


@bp.route("/")
def index():
    db = get_db()
    loads = db.execute("SELECT * FROM data_loads ORDER BY loaded_at DESC LIMIT 200").fetchall()
    return render_template("data_load_history.html", loads=loads)
