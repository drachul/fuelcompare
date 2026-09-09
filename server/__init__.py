from flask import Flask


def create_app() -> Flask:
    app = Flask(
        __name__,
        static_folder="../static",
        template_folder="../templates",
    )

    from .routes import bp as api_bp
    app.register_blueprint(api_bp, url_prefix="/api")

    from flask import render_template

    @app.route("/")
    def index():
        return render_template("index.html")

    return app
