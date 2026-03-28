from datetime import datetime, timezone

from flask_login import UserMixin

from app import db, login_manager


def utc_now():
    return datetime.now(timezone.utc)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    evaluations = db.relationship("EvaluationResult", backref="user", lazy=True)
    listings = db.relationship("Listing", backref="user", lazy=True)

    def __repr__(self):
        return f"<User {self.email}>"


class EvaluationResult(db.Model):
    __tablename__ = "evaluation_results"

    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(64), unique=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    input_json = db.Column(db.Text, nullable=False)
    result_json = db.Column(db.Text, nullable=False)

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    def __repr__(self):
        return f"<EvaluationResult {self.token}>"


class Listing(db.Model):
    __tablename__ = "listings"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    title = db.Column(db.String(255), nullable=False)
    brand = db.Column(db.String(100), nullable=True)
    model_family = db.Column(db.String(100), nullable=True)
    ram_gb = db.Column(db.Integer, nullable=True)
    price_asked = db.Column(db.Float, nullable=False)
    condition = db.Column(db.String(50), nullable=True)
    description = db.Column(db.Text, nullable=True)

    evaluation_token = db.Column(db.String(64), nullable=True, unique=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    def __repr__(self):
        return f"<Listing {self.title}>"


@login_manager.user_loader
def load_user(user_id):
    try:
        return db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None