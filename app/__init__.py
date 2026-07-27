import os

from flask import Flask

from .auth import ROLE_LABELS, can_preview_roles, get_current_user
from .config import Config
from . import db as db_module
from .importer import start_importer_thread
from .timeutils import now_central


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    os.makedirs(app.config["DATA_DIR"], exist_ok=True)
    db_module.init_app(app)
    db_module.init_db(app.config["DB_PATH"])
    db_module.seed_default_settings(
        app.config["DB_PATH"],
        {
            "incoming_dir": app.config["DEFAULT_INCOMING_DIR"],
            "backup_dir": app.config["DEFAULT_BACKUP_DIR"],
            "watch_interval_seconds": str(app.config["DEFAULT_WATCH_INTERVAL_SECONDS"]),
        },
    )

    from .routes.overview import bp as overview_bp
    from .routes.reports import bp as reports_bp
    from .routes.signoffs import bp as signoffs_bp
    from .routes.followups import bp as followups_bp
    from .routes.draft_notes import bp as draft_notes_bp
    from .routes.data_loads import bp as data_loads_bp
    from .routes.admin import bp as admin_bp
    from .routes.account import bp as account_bp

    app.register_blueprint(overview_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(signoffs_bp)
    app.register_blueprint(followups_bp)
    app.register_blueprint(draft_notes_bp)
    app.register_blueprint(data_loads_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(account_bp)

    @app.context_processor
    def inject_globals():
        return {
            "now": now_central(),
            "current_user": get_current_user(),
            "can_preview_roles": can_preview_roles(),
            "role_labels": ROLE_LABELS,
        }

    start_importer_thread(app.config["DB_PATH"])

    return app
