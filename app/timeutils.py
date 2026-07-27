"""Central Time helpers.

The plant operates on US Central Time. We deliberately avoid SQLite's
datetime('now','localtime') and Python's naive datetime.now() for anything
displayed/stored, since both follow the server OS's configured timezone
(which may not be Central on every machine this app runs on). Instead we
always compute Central Time explicitly here.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

PLANT_TIMEZONE = ZoneInfo("America/Chicago")


def now_central():
    """Current timezone-aware datetime in US Central Time."""
    return datetime.now(PLANT_TIMEZONE)


def now_central_str():
    """Current Central Time as 'YYYY-MM-DD HH:MM:SS' (matches existing TEXT columns)."""
    return now_central().strftime("%Y-%m-%d %H:%M:%S")


def today_central_str():
    """Current Central Time date as 'YYYY-MM-DD'."""
    return now_central().date().isoformat()


def filename_timestamp():
    """Compact timestamp for filenames, e.g. 20260727_113000."""
    return now_central().strftime("%Y%m%d_%H%M%S")
