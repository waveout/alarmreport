import glob
import logging
import os
import re
import shutil
import threading
import time

import pandas as pd

from .db import get_connection, get_setting
from .timeutils import filename_timestamp, now_central_str

logger = logging.getLogger("importer")

# Matches filenames like "FOX_SCHERER_1_ALARMS...", "SCHERER 2 Daily...", or "UNIT_3_..."
# to identify which of the plant's 3 units a CSV export belongs to. Uses (?!\d) instead of \b
# since \b does not separate a digit from an adjacent underscore (both are "word" characters).
_UNIT_PATTERN = re.compile(r"(?:SCHERER|UNIT)[\s_-]*([1-3])(?!\d)", re.IGNORECASE)


def _extract_unit(filename):
    """Best-effort detection of the generating unit (1, 2, or 3) from a filename.
    Returns None if no unit could be determined."""
    match = _UNIT_PATTERN.search(filename)
    return int(match.group(1)) if match else None

# Normalized (stripped/upper-cased) CSV header -> alarms table column.
COLUMN_MAP = {
    "DATE": "alarm_date",
    "COMPOUND": "compound",
    "BLOCK": "block",
    "DESCRIPTION": "description",
    "NAME": "name",
    "ALARM TYPE": "alarm_type",
    "ALARM TYPE TYPE": "alarm_type",
    "TYPE": "alarm_type",
    "ALARM DESC": "alarm_desc",
    "ALM_RTN": "alm_rtn",
    "PRIORITY": "priority",
    "VALUE": "value",
    "ALARM VALUE": "alarm_value",
    "UNITS": "units",
    "LOCATION": "location",
    "GRP": "grp",
}

ALARM_COLUMNS = [
    "alarm_date",
    "compound",
    "block",
    "description",
    "name",
    "alarm_type",
    "alarm_desc",
    "alm_rtn",
    "priority",
    "value",
    "alarm_value",
    "units",
    "location",
    "grp",
]


def _is_file_stable(path, wait_seconds=1.0):
    """Guard against reading a file while it is still being written/copied."""
    try:
        size_before = os.path.getsize(path)
        time.sleep(wait_seconds)
        size_after = os.path.getsize(path)
        return size_before == size_after
    except OSError:
        return False


def _read_csv(path):
    # encoding="utf-8-sig" strips a leading UTF-8 BOM if present (common in exports from
    # historian/SCADA tools), which would otherwise corrupt the first header (e.g. "\ufeffDATE")
    # and cause it to silently fail to match COLUMN_MAP.
    df = pd.read_csv(
        path, sep=None, engine="python", dtype=str, keep_default_na=False, na_values=[""], encoding="utf-8-sig"
    )
    df.columns = [str(col).strip().upper() for col in df.columns]

    rename_map = {col: COLUMN_MAP[col] for col in df.columns if col in COLUMN_MAP}
    df = df.rename(columns=rename_map)

    for col in ALARM_COLUMNS:
        if col not in df.columns:
            df[col] = None
    df = df[ALARM_COLUMNS].copy()

    df["alarm_date"] = pd.to_datetime(df["alarm_date"], errors="coerce").dt.strftime("%Y-%m-%d %H:%M:%S")

    priority_numeric = pd.to_numeric(df["priority"], errors="coerce")
    df["priority"] = priority_numeric.apply(lambda v: int(v) if pd.notnull(v) else None)

    df = df.astype(object).where(pd.notnull(df), None)
    return df


def import_file(conn, path):
    """Parse a CSV file and insert its rows into alarms within a single transaction.
    Returns (data_load_id, row_count)."""
    df = _read_csv(path)
    rows = df.values.tolist()
    unit = _extract_unit(os.path.basename(path))

    cur = conn.cursor()
    cur.execute(
        "INSERT INTO data_loads (filename, status, row_count, unit, loaded_at) VALUES (?, 'in_progress', 0, ?, ?)",
        (os.path.basename(path), unit, now_central_str()),
    )
    load_id = cur.lastrowid

    placeholders = ",".join("?" for _ in ALARM_COLUMNS)
    insert_sql = (
        f"INSERT INTO alarms ({','.join(ALARM_COLUMNS)}, unit, data_load_id, created_at) "
        f"VALUES ({placeholders}, ?, ?, ?)"
    )
    imported_at = now_central_str()
    cur.executemany(insert_sql, [row + [unit, load_id, imported_at] for row in rows])

    cur.execute(
        "UPDATE data_loads SET status = 'success', row_count = ? WHERE id = ?",
        (len(rows), load_id),
    )
    conn.commit()
    return load_id, len(rows)


def process_incoming_folder(db_path):
    conn = get_connection(db_path)
    try:
        incoming_dir = get_setting(conn, "incoming_dir")
        backup_dir = get_setting(conn, "backup_dir")
        os.makedirs(incoming_dir, exist_ok=True)
        os.makedirs(backup_dir, exist_ok=True)

        csv_files = sorted(glob.glob(os.path.join(incoming_dir, "*.csv")))
        for path in csv_files:
            if not _is_file_stable(path):
                continue
            filename = os.path.basename(path)
            try:
                load_id, row_count = import_file(conn, path)

                stem, ext = os.path.splitext(filename)
                backup_name = f"{stem}_{filename_timestamp()}{ext}"
                backup_path = os.path.join(backup_dir, backup_name)
                shutil.move(path, backup_path)

                conn.execute(
                    "UPDATE data_loads SET backup_filename = ? WHERE id = ?",
                    (backup_name, load_id),
                )
                conn.commit()
                logger.info("Imported %s row(s) from %s (data_load_id=%s)", row_count, filename, load_id)
            except Exception as exc:  # noqa: BLE001 - log and continue with next file
                conn.rollback()
                logger.exception("Failed to import %s", filename)
                conn.execute(
                    "INSERT INTO data_loads (filename, status, row_count, error_message, unit, loaded_at) "
                    "VALUES (?, 'failed', 0, ?, ?, ?)",
                    (filename, str(exc), _extract_unit(filename), now_central_str()),
                )
                conn.commit()
    finally:
        conn.close()


def _watch_loop(db_path):
    while True:
        try:
            process_incoming_folder(db_path)
        except Exception:  # noqa: BLE001 - never let the watcher thread die
            logger.exception("Unexpected error while scanning incoming folder")

        conn = get_connection(db_path)
        try:
            interval = int(get_setting(conn, "watch_interval_seconds", 30))
        finally:
            conn.close()
        time.sleep(max(interval, 5))


def start_importer_thread(db_path):
    thread = threading.Thread(target=_watch_loop, args=(db_path,), daemon=True, name="csv-importer")
    thread.start()
    logger.info("CSV importer thread started (watching for files every N seconds)")
    return thread
