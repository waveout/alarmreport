import getpass

from flask import session

from .db import get_db

# The role a Windows account is mapped to, in the `users` table.
ROLE_LABELS = {
    "bto": "BTO",
    "team_leader": "Team Leader",
    "manager": "Manager",
    "viewer": "Viewer",
}
VALID_ROLES = tuple(ROLE_LABELS.keys())

# Testing-only feature: this single Windows account may temporarily "preview" the
# app as any role (BTO / Team Leader / Manager / Viewer) without needing separate
# registered test accounts. No other account can use this.
PREVIEW_ROLE_USERNAME = "dhjenkin"


def detect_windows_username():
    """Best-effort detection of the OS account running this process.
    Note: with the Flask dev server this reflects the account the server
    process runs under, not necessarily the browser's Windows session if
    accessed remotely over a LAN. Users can override via /account/switch."""
    try:
        return getpass.getuser()
    except Exception:  # noqa: BLE001
        return None


def can_preview_roles():
    """Only the designated test account may preview other roles."""
    detected = detect_windows_username()
    return bool(detected) and detected.lower() == PREVIEW_ROLE_USERNAME.lower()


def role_label(role):
    return ROLE_LABELS.get(role, role)


def _user_dict(row):
    return {
        "id": row["id"],
        "windows_username": row["windows_username"],
        "display_name": row["display_name"],
        "role": row["role"],
        "registered": True,
    }


def get_current_user():
    db = get_db()

    override_id = session.get("override_user_id")
    if override_id:
        row = db.execute("SELECT * FROM users WHERE id = ?", (override_id,)).fetchone()
        if row:
            return _user_dict(row)
        session.pop("override_user_id", None)

    detected = detect_windows_username()
    row = None
    if detected:
        row = db.execute(
            "SELECT * FROM users WHERE lower(windows_username) = lower(?)", (detected,)
        ).fetchone()
    if row:
        user = _user_dict(row)
    else:
        user = {
            "id": None,
            "windows_username": detected or "unknown",
            "display_name": detected or "Unknown User",
            "role": "viewer",
            "registered": False,
        }

    preview_role = session.get("preview_role")
    if preview_role and can_preview_roles():
        user = dict(user)
        user["role"] = preview_role
        user["previewing"] = True

    return user


def is_bto(user):
    return user["role"] == "bto"
