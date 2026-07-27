import logging

from app import create_app

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

app = create_app()

if __name__ == "__main__":
    # use_reloader=False avoids spawning a second process (which would start
    # a second background CSV-importer thread).
    app.run(debug=True, use_reloader=False)
