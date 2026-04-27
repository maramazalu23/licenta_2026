from datetime import datetime, timezone

from flask_login import UserMixin

from app import db, login_manager


def utc_now():
    return datetime.now(timezone.utc)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    ROLE_ADMIN = "admin"
    ROLE_SELLER = "seller"
    ROLE_BUYER = "buyer"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default=ROLE_BUYER, index=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    evaluations = db.relationship("EvaluationResult", backref="user", lazy=True)
    listings = db.relationship("Listing", backref="user", lazy=True)

    favorites = db.relationship(
        "Favorite",
        backref="user",
        lazy=True,
        cascade="all, delete-orphan",
    )

    notifications = db.relationship(
        "Notification",
        backref="user",
        lazy=True,
        cascade="all, delete-orphan",
    )

    @property
    def is_admin(self):
        return self.role == self.ROLE_ADMIN

    @property
    def is_seller(self):
        return self.role == self.ROLE_SELLER

    @property
    def is_buyer(self):
        return self.role == self.ROLE_BUYER

    def __repr__(self):
        return f"<User {self.email} ({self.role})>"


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
    brand = db.Column(db.String(100), nullable=True, index=True)
    model_family = db.Column(db.String(100), nullable=True, index=True)
    ram_gb = db.Column(db.Integer, nullable=True, index=True)
    price_asked = db.Column(db.Float, nullable=False)
    condition = db.Column(db.String(50), nullable=True, index=True)
    description = db.Column(db.Text, nullable=True)
    image_filename = db.Column(db.String(255), nullable=True)

    recommended_price = db.Column(db.Float, nullable=True)
    deal_score = db.Column(db.Float, nullable=True)

    evaluation_token = db.Column(db.String(64), nullable=True, unique=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    favorite_entries = db.relationship(
        "Favorite",
        backref="listing",
        lazy=True,
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<Listing {self.title}>"


class Favorite(db.Model):
    __tablename__ = "favorites"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    listing_id = db.Column(db.Integer, db.ForeignKey("listings.id"), nullable=False, index=True)

    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    __table_args__ = (
        db.UniqueConstraint(
            "user_id",
            "listing_id",
            name="uq_favorite_user_listing",
        ),
    )

    def __repr__(self):
        return f"<Favorite user={self.user_id} listing={self.listing_id}>"


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)

    type = db.Column(db.String(50), nullable=False, default="generic", index=True)
    title = db.Column(db.String(255), nullable=False)
    message = db.Column(db.Text, nullable=False)

    brand = db.Column(db.String(100), nullable=True, index=True)
    model_family = db.Column(db.String(100), nullable=True, index=True)
    ram_gb = db.Column(db.Integer, nullable=True, index=True)

    is_read = db.Column(db.Boolean, nullable=False, default=False, index=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    read_at = db.Column(db.DateTime, nullable=True)

    def __repr__(self):
        return f"<Notification {self.id} user={self.user_id} read={self.is_read}>"


@login_manager.user_loader
def load_user(user_id):
    try:
        return db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None