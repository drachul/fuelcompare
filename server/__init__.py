import os
from pathlib import Path

from flask import Flask


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(
        __name__,
        static_folder="../static",
        template_folder="../templates",
    )
    app.config.from_mapping(
        VEHICLE_DB_PATH=os.environ.get(
            "FUELCOMPARE_DB_PATH",
            str(Path(app.root_path).parent / "data" / "fuelcompare.db"),
        ) or str(Path(app.root_path).parent / "data" / "fuelcompare.db")
    )
    if test_config:
        app.config.update(test_config)

    from . import vehicle_store
    vehicle_store.init_app(app)

    from .routes import bp as api_bp
    app.register_blueprint(api_bp, url_prefix="/api")

    from flask import render_template

    @app.route("/")
    def index():
        return render_template("index.html")

    return app
