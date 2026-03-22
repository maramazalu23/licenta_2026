from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

from app import db
from app.models import User


auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


def _validate_register_form(email, password, password_confirm):
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
        return redirect(url_for("main.profile"))

    form_data = {
        "email": "",
    }
    errors = {}

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        password_confirm = request.form.get("password_confirm", "")

        form_data["email"] = email
        errors = _validate_register_form(email, password, password_confirm)

        if errors:
            flash("Formularul de înregistrare conține erori.", "warning")
            return render_template("register.html", form_data=form_data, errors=errors)

        user = User(
            email=email,
            password_hash=generate_password_hash(password),
        )
        db.session.add(user)
        db.session.commit()

        login_user(user)
        flash("Contul a fost creat cu succes.", "success")
        return redirect(url_for("main.profile"))

    return render_template("register.html", form_data=form_data, errors=errors)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.profile"))

    form_data = {
        "email": "",
    }
    errors = {}

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        form_data["email"] = email
        errors = _validate_login_form(email, password)

        if not errors:
            user = User.query.filter_by(email=email).first()
            if not user or not check_password_hash(user.password_hash, password):
                errors["general"] = "Email sau parolă incorecte."

        if errors:
            flash("Autentificarea a eșuat. Verifică datele introduse.", "warning")
            return render_template("login.html", form_data=form_data, errors=errors)

        login_user(user)
        flash("Te-ai autentificat cu succes.", "success")
        return redirect(url_for("main.profile"))

    return render_template("login.html", form_data=form_data, errors=errors)


@auth_bp.route("/logout", methods=["POST"])
def logout():
    if current_user.is_authenticated:
        logout_user()
        flash("Te-ai delogat cu succes.", "success")
    return redirect(url_for("main.index"))