from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

from app import db
from app.models import User
from app.services import claim_evaluation_for_user


auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


PUBLIC_ROLES = {User.ROLE_SELLER, User.ROLE_BUYER}


def _safe_next_url():
    next_url = request.values.get("next", "").strip()
    if not next_url:
        return None
    if not next_url.startswith("/"):
        return None
    if next_url.startswith("//"):
        return None
    return next_url


def _default_redirect_for_user(user):
    if user.is_admin:
        return url_for("main.admin_dashboard")
    if user.is_seller:
        return url_for("main.profile")
    return url_for("main.index")


def _redirect_after_login(user, next_url):
    if next_url:
        if next_url.startswith("/publish/"):
            token = next_url.removeprefix("/publish/").strip("/")
            if token:
                return url_for("main.result_page", token=token)
            return _default_redirect_for_user(user)

        return next_url

    return _default_redirect_for_user(user)


def _token_from_next_url(next_url):
    if not next_url:
        return None

    prefixes = ("/publish/", "/result/")
    for prefix in prefixes:
        if next_url.startswith(prefix):
            token = next_url[len(prefix):].strip("/")
            return token or None

    return None


def _validate_register_form(email, password, password_confirm, role):
    errors = {}

    if not email:
        errors["email"] = "Completează adresa de email."
    elif "@" not in email or "." not in email:
        errors["email"] = "Adresa de email nu este validă."

    if not password:
        errors["password"] = "Completează parola."
    elif len(password) < 6:
        errors["password"] = "Parola trebuie să aibă cel puțin 6 caractere."

    if not password_confirm:
        errors["password_confirm"] = "Confirmă parola."
    elif password != password_confirm:
        errors["password_confirm"] = "Parolele nu coincid."

    if not role:
        errors["role"] = "Selectează tipul de cont."
    elif role not in PUBLIC_ROLES:
        errors["role"] = "Rol invalid."

    existing = User.query.filter_by(email=email).first() if email else None
    if existing:
        errors["email"] = "Există deja un cont cu acest email."

    return errors


def _validate_login_form(email, password):
    errors = {}

    if not email:
        errors["email"] = "Completează adresa de email."
    if not password:
        errors["password"] = "Completează parola."

    return errors


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(_default_redirect_for_user(current_user))

    form_data = {
        "email": "",
        "role": User.ROLE_BUYER,
    }
    errors = {}
    next_url = _safe_next_url()

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        password_confirm = request.form.get("password_confirm", "")
        role = request.form.get("role", "").strip()

        form_data["email"] = email
        form_data["role"] = role

        errors = _validate_register_form(email, password, password_confirm, role)

        if errors:
            flash("Formularul de înregistrare conține erori.", "warning")
            return render_template(
                "register.html",
                form_data=form_data,
                errors=errors,
                next_url=next_url,
            )

        user = User(
            email=email,
            password_hash=generate_password_hash(password),
            role=role,
        )
        db.session.add(user)
        db.session.commit()

        login_user(user)
        flash("Contul a fost creat cu succes.", "success")

        token = _token_from_next_url(next_url)
        if token:
            claim_evaluation_for_user(token, user.id)

        return redirect(_redirect_after_login(user, next_url))

    return render_template(
        "register.html",
        form_data=form_data,
        errors=errors,
        next_url=next_url,
    )


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(_default_redirect_for_user(current_user))

    form_data = {
        "email": "",
    }
    errors = {}
    next_url = _safe_next_url()

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        form_data["email"] = email
        errors = _validate_login_form(email, password)

        user = None
        if not errors:
            user = User.query.filter_by(email=email).first()
            if not user or not check_password_hash(user.password_hash, password):
                errors["general"] = "Email sau parolă incorecte."

        if errors:
            flash("Autentificarea a eșuat. Verifică datele introduse.", "warning")
            return render_template(
                "login.html",
                form_data=form_data,
                errors=errors,
                next_url=next_url,
            )

        login_user(user)
        flash("Te-ai autentificat cu succes.", "success")

        token = _token_from_next_url(next_url)
        if token:
            claim_evaluation_for_user(token, user.id)

        # Aici vom putea adăuga mai târziu generarea notificărilor pentru seller.
        return redirect(_redirect_after_login(user, next_url))

    return render_template(
        "login.html",
        form_data=form_data,
        errors=errors,
        next_url=next_url,
    )


@auth_bp.route("/logout", methods=["POST"])
def logout():
    if current_user.is_authenticated:
        logout_user()
        flash("Te-ai delogat cu succes.", "success")
    return redirect(url_for("main.index"))