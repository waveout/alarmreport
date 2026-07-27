from datetime import timedelta

from flask import Blueprint, render_template, request

from ..auth import get_current_user
from ..db import get_db
from ..timeutils import now_central

bp = Blueprint("overview", __name__)


def _resolve_since(range_param):
    now = now_central()
    if range_param == "24h":
        return now - timedelta(hours=24)
    if range_param == "7d":
        return now - timedelta(days=7)
    if range_param == "30d":
        return now - timedelta(days=30)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)  # "today"


def _unit_summary(db, since_str, unit):
    unit_clause = " AND unit = ?" if unit else ""
    unit_params = [unit] if unit else []

    counts = {1: 0, 2: 0, 3: 0}
    for row in db.execute(
        f"SELECT priority, COUNT(*) AS cnt FROM alarms WHERE alarm_date >= ?{unit_clause} GROUP BY priority",
        [since_str, *unit_params],
    ):
        if row["priority"] in (1, 2, 3):
            counts[int(row["priority"])] = row["cnt"]
    total = sum(counts.values())

    last_alarm = db.execute(
        f"SELECT alarm_date FROM alarms WHERE 1=1{unit_clause} ORDER BY alarm_date DESC LIMIT 1",
        unit_params,
    ).fetchone()

    return {"unit": unit, "counts": counts, "total": total, "last_alarm": last_alarm}


def _bucketed_series(db, since_dt, now_dt, range_param, unit_clause, unit_params):
    """Build hourly (today/24h) or daily (7d/30d) priority-breakdown series for charts."""
    is_hourly = range_param in ("today", "24h")
    bucket_len = 13 if is_hourly else 10  # "YYYY-MM-DD HH" or "YYYY-MM-DD"
    step = timedelta(hours=1) if is_hourly else timedelta(days=1)
    key_fmt = "%Y-%m-%d %H" if is_hourly else "%Y-%m-%d"
    label_fmt = "%I %p" if is_hourly else "%m/%d"
    start = since_dt.replace(minute=0, second=0, microsecond=0)
    if not is_hourly:
        start = start.replace(hour=0)

    since_str = since_dt.strftime("%Y-%m-%d %H:%M:%S")
    rows = db.execute(
        f"""
        SELECT substr(alarm_date, 1, {bucket_len}) AS bucket, priority, COUNT(*) AS cnt
        FROM alarms
        WHERE alarm_date >= ? AND priority IN (1, 2, 3){unit_clause}
        GROUP BY bucket, priority
        """,
        [since_str, *unit_params],
    ).fetchall()

    counts_by_bucket = {}
    for row in rows:
        counts_by_bucket.setdefault(row["bucket"], {})[int(row["priority"])] = row["cnt"]

    labels, p1, p2, p3, total = [], [], [], [], []
    cursor = start
    while cursor <= now_dt:
        bucket_counts = counts_by_bucket.get(cursor.strftime(key_fmt), {})
        c1 = bucket_counts.get(1, 0)
        c2 = bucket_counts.get(2, 0)
        c3 = bucket_counts.get(3, 0)
        labels.append(cursor.strftime(label_fmt))
        p1.append(c1)
        p2.append(c2)
        p3.append(c3)
        total.append(c1 + c2 + c3)
        cursor += step

    return {"labels": labels, "p1": p1, "p2": p2, "p3": p3, "total": total}


@bp.route("/")
def index():
    db = get_db()
    current_user = get_current_user()
    range_param = request.args.get("range", "today")
    since_dt = _resolve_since(range_param)
    since_str = since_dt.strftime("%Y-%m-%d %H:%M:%S")
    now_dt = now_central()

    is_manager = current_user["role"] == "manager"
    unit_specified = "unit" in request.args

    if is_manager and not unit_specified:
        plant = _unit_summary(db, since_str, None)
        unit_summaries = [_unit_summary(db, since_str, u) for u in (1, 2, 3)]

        top_equipment = db.execute(
            """
            SELECT description, COUNT(*) AS cnt FROM alarms
            WHERE alarm_date >= ? AND description IS NOT NULL AND description != ''
            GROUP BY description ORDER BY cnt DESC LIMIT 5
            """,
            [since_str],
        ).fetchall()

        last_load = db.execute(
            "SELECT loaded_at, status FROM data_loads ORDER BY loaded_at DESC LIMIT 1"
        ).fetchone()

        chart_series = _bucketed_series(db, since_dt, now_dt, range_param, "", [])

        return render_template(
            "manager_dashboard.html",
            plant=plant,
            unit_summaries=unit_summaries,
            top_equipment=top_equipment,
            last_load=last_load,
            since_dt=since_dt,
            range_param=range_param,
            chart_series=chart_series,
        )

    unit_param = request.args.get("unit", "all")
    unit_clause = ""
    unit_params = []
    if unit_param in ("1", "2", "3"):
        unit_clause = " AND unit = ?"
        unit_params.append(int(unit_param))

    counts = {1: 0, 2: 0, 3: 0}
    for row in db.execute(
        f"SELECT priority, COUNT(*) AS cnt FROM alarms WHERE alarm_date >= ?{unit_clause} GROUP BY priority",
        [since_str, *unit_params],
    ):
        if row["priority"] in (1, 2, 3):
            counts[int(row["priority"])] = row["cnt"]
    total = sum(counts.values())

    last_alarm = db.execute(
        f"SELECT alarm_date FROM alarms WHERE 1=1{unit_clause} ORDER BY alarm_date DESC LIMIT 1",
        unit_params,
    ).fetchone()
    last_load = db.execute(
        f"SELECT loaded_at, status FROM data_loads WHERE 1=1{unit_clause} ORDER BY loaded_at DESC LIMIT 1",
        unit_params,
    ).fetchone()

    top_equipment = db.execute(
        f"""
        SELECT description, unit, COUNT(*) AS cnt FROM alarms
        WHERE alarm_date >= ? AND description IS NOT NULL AND description != ''{unit_clause}
        GROUP BY description, unit ORDER BY cnt DESC LIMIT 10
        """,
        [since_str, *unit_params],
    ).fetchall()

    recent_p1 = db.execute(
        f"""
        SELECT alarm_date, description, alarm_desc, unit FROM alarms
        WHERE priority = 1{unit_clause} ORDER BY alarm_date DESC LIMIT 10
        """,
        unit_params,
    ).fetchall()

    chart_series = _bucketed_series(db, since_dt, now_dt, range_param, unit_clause, unit_params)

    return render_template(
        "overview.html",
        counts=counts,
        total=total,
        last_alarm=last_alarm,
        last_load=last_load,
        top_equipment=top_equipment,
        recent_p1=recent_p1,
        since_dt=since_dt,
        range_param=range_param,
        unit_param=unit_param,
        is_manager=is_manager,
        chart_series=chart_series,
    )

