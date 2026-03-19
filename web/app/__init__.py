from flask import Flask, get_flashed_messages
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager


db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = "auth.login"


def format_price(value):
    if value is None or value == "":
        return "N/A"
    try:
        return f"{float(value):,.2f} RON".replace(",", "X").replace(".", ",").replace("X", ".")
    except (TypeError, ValueError):
        return str(value)


def format_number(value):
    if value is None or value == "":
        return "N/A"
    try:
        return f"{float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (TypeError, ValueError):
        return str(value)


def format_pct(value):
    if value is None or value == "":
        return "N/A"
    try:
        return f"{float(value):.2f}%".replace(".", ",")
    except (TypeError, ValueError):
        return str(value)


def create_app():
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_object("config.Config")

    db.init_app(app)
    login_manager.init_app(app)

    app.jinja_env.filters["price"] = format_price
    app.jinja_env.filters["num"] = format_number
    app.jinja_env.filters["pct"] = format_pct

    from app.routes import main_bp
    app.register_blueprint(main_bp)

    from app import models

    with app.app_context():
        db.create_all()

    @app.context_processor
    def inject_flash_messages():
        return {"flashed_messages": get_flashed_messages(with_categories=True)}

    return app