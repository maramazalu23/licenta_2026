from functools import wraps

from flask import Blueprint, render_template, request, redirect, url_for, abort, flash
from flask_login import current_user, login_required

from app.models import User
from app.scoring.service import evaluate_listing
from app.db_market import (
    get_market_summary,
    get_explore_filters,
    get_explore_products,
    get_similar_products,
)
from app.services import (
    save_evaluation,
    get_evaluation_by_token,
    is_listing_published,
    create_listing_from_evaluation,
    list_recent_listings,
    list_user_evaluations,
    list_user_listings,
    list_recent_evaluations,
    list_admin_evaluations,
    get_admin_history_filters,
    add_favorite,
    remove_favorite,
    list_user_favorites,
    build_favorite_listing_ids,
    list_recommended_listings_for_buyer,
    list_user_notifications,
    count_unread_notifications,
    mark_notification_as_read,
    mark_all_notifications_as_read,
    generate_seller_notifications_for_user,
    refresh_seller_notifications_for_listing_segment,
    can_user_publish_evaluation,
)


main_bp = Blueprint("main", __name__)


def role_required(*allowed_roles):
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapped_view(*args, **kwargs):
            if current_user.role not in allowed_roles:
                flash("Nu ai permisiunea să accesezi această pagină.", "danger")
                return redirect(url_for("main.index"))
            return view_func(*args, **kwargs)
        return wrapped_view
    return decorator


@main_bp.app_context_processor
def inject_notification_counts():
    unread_notifications_count = 0

    if current_user.is_authenticated and current_user.is_seller:
        unread_notifications_count = count_unread_notifications(current_user.id)

    return {
        "unread_notifications_count": unread_notifications_count,
    }


def _to_int(value):
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _to_float(value):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clean_condition(value):
    value = str(value).strip().lower() if value is not None else ""
    return value if value in {"used", "new"} else "used"


def _deal_label_ro(label):
    mapping = {
        "very_good": "Foarte avantajos",
        "good": "Avantajos",
        "fair": "Corect",
        "slightly_high": "Ușor ridicat",
        "high": "Ridicat",
        "overpriced": "Supraevaluat",
        "unknown": "Necunoscut",
    }
    return mapping.get(label, label or "Necunoscut")


def _depreciation_label_ro(label):
    mapping = {
        "healthy": "Depreciere sănătoasă",
        "low_depreciation": "Depreciere redusă",
        "very_low_depreciation": "Depreciere foarte redusă",
        "high_depreciation": "Depreciere ridicată",
        "extreme_depreciation": "Depreciere extremă",
        "unknown": "Necunoscut",
        "not_applicable": "Nu se aplică",
    }
    return mapping.get(label, label or "Necunoscut")


def _attractiveness_label_ro(label):
    mapping = {
        "excellent": "Excelent",
        "good": "Bun",
        "average": "Mediu",
        "weak": "Slab",
    }
    return mapping.get(label, label or "Necunoscut")


def _score_badge_class(score):
    if score is None:
        return "bg-secondary"
    if score >= 85:
        return "bg-success"
    if score >= 65:
        return "bg-primary"
    if score >= 45:
        return "bg-warning text-dark"
    return "bg-danger"


def _validate_form(form_data, filters):
    errors = {}

    allowed_brands = set(filters.get("brands", []))
    allowed_families = set(filters.get("families", []))
    allowed_ram = {str(x) for x in filters.get("ram_options", [])}

    if not form_data["title"]:
        errors["title"] = "Completează titlul anunțului."

    if not form_data["brand"]:
        errors["brand"] = "Selectează un brand."
    elif form_data["brand"] not in allowed_brands:
        errors["brand"] = "Brand invalid."

    if form_data["model_family"] and form_data["model_family"] not in allowed_families:
        errors["model_family"] = "Familie de model invalidă."

    if not form_data["ram_gb"]:
        errors["ram_gb"] = "Selectează cantitatea de RAM."
    elif form_data["ram_gb"] not in allowed_ram:
        errors["ram_gb"] = "Valoare RAM invalidă."

    if not form_data["condition"]:
        errors["condition"] = "Selectează condiția produsului."
    elif form_data["condition"] not in {"used", "new"}:
        errors["condition"] = "Condiție invalidă."

    if not form_data["price_asked"]:
        errors["price_asked"] = "Completează prețul cerut."
    else:
        price = _to_float(form_data["price_asked"])
        if price is None:
            errors["price_asked"] = "Prețul cerut trebuie să fie numeric."
        elif price <= 0:
            errors["price_asked"] = "Prețul cerut trebuie să fie mai mare decât 0."

    if form_data["description"] and len(form_data["description"]) < 15:
        errors["description"] = "Descrierea este prea scurtă. Adaugă mai multe detalii sau las-o goală."

    return errors


def _normalize_saved_result(result, form_input=None):
    if not result:
        return result

    price_estimation = result.setdefault("price_estimation", {})
    outputs = price_estimation.setdefault("outputs", {})
    market_reference = price_estimation.setdefault("market_reference", {})
    segment = price_estimation.setdefault("segment", {})
    explanations = price_estimation.setdefault("explanations", {})
    depreciation = result.setdefault("depreciation", {})
    attractiveness = result.setdefault("attractiveness", {})

    selected_condition = None
    if isinstance(result.get("input"), dict):
        selected_condition = result["input"].get("condition")
    if not selected_condition and isinstance(form_input, dict):
        selected_condition = form_input.get("condition")
    selected_condition = _clean_condition(selected_condition)

    outputs.setdefault("selected_condition", selected_condition)

    fair_price_used = outputs.get("fair_price_used")
    fair_price_new = outputs.get("fair_price_new")
    fair_price = outputs.get("fair_price")

    if fair_price is None:
        outputs["fair_price"] = fair_price_new if selected_condition == "new" else fair_price_used

    outputs.setdefault("fair_price_new", fair_price_new)
    outputs.setdefault("fair_price_used", fair_price_used)

    outputs.setdefault("deal_rating_label", "unknown")
    outputs.setdefault("deal_rating_score", None)
    outputs.setdefault("delta_vs_fair_price", None)

    market_reference.setdefault("used_q1", None)
    market_reference.setdefault("used_median", None)
    market_reference.setdefault("used_q3", None)
    market_reference.setdefault("new_median", None)

    segment.setdefault("source_level", "no_match")
    segment.setdefault("confidence", "very_low")
    segment.setdefault("filters_used", {})
    segment.setdefault("used_n", 0)
    segment.setdefault("new_n", 0)

    explanations.setdefault("pricing", "Evaluare încărcată din istoric.")
    explanations.setdefault("deal", "Explicație indisponibilă pentru această evaluare salvată.")

    depreciation.setdefault("score", None)
    depreciation.setdefault("retention_ratio", None)
    depreciation.setdefault("depreciation_pct", None)
    depreciation.setdefault("label", "unknown")
    depreciation.setdefault("explanation", "Nu există suficiente date pentru estimarea deprecierii.")

    attractiveness.setdefault("score", None)
    attractiveness.setdefault("label", "weak")
    attractiveness.setdefault("explanation", "Nu există suficiente date pentru evaluarea atractivității.")
    attractiveness.setdefault("recommendations", [])

    return result


def _decorate_result_for_ui(result):
    result = _normalize_saved_result(result, form_input=result.get("input"))

    result["ui"] = {
        "deal_label_ro": _deal_label_ro(result["price_estimation"]["outputs"].get("deal_rating_label")),
        "depreciation_label_ro": _depreciation_label_ro(result["depreciation"].get("label")),
        "attractiveness_label_ro": _attractiveness_label_ro(result["attractiveness"].get("label")),
        "deal_badge_class": _score_badge_class(result["price_estimation"]["outputs"].get("deal_rating_score")),
        "depreciation_badge_class": _score_badge_class(result["depreciation"].get("score")),
        "attractiveness_badge_class": _score_badge_class(result["attractiveness"].get("score")),
    }
    return result


@main_bp.route("/")
def index():
    if current_user.is_authenticated and current_user.is_admin:
        return redirect(url_for("main.admin_dashboard"))

    summary = get_market_summary()

    seller_overview = None
    buyer_overview = None
    recommended_listings = []

    if current_user.is_authenticated and current_user.is_seller:
        seller_evaluations = list_user_evaluations(current_user.id, limit=20)
        seller_listings = list_user_listings(current_user.id, limit=20)

        avg_deal_score = None
        valid_scores = [row["deal_score"] for row in seller_evaluations if row.get("deal_score") is not None]
        if valid_scores:
            avg_deal_score = round(sum(valid_scores) / len(valid_scores), 2)

        seller_overview = {
            "listings_count": len(seller_listings),
            "evaluations_count": len(seller_evaluations),
            "avg_deal_score": avg_deal_score,
        }

    if current_user.is_authenticated and current_user.is_buyer:
        recommended_listings = list_recommended_listings_for_buyer(current_user.id, limit=6)

        if recommended_listings:
            buyer_message = "Ți-am pregătit sugestii pe baza anunțurilor salvate la favorite."
        else:
            buyer_message = "Poți analiza piața în Explore și salva anunțuri favorite din platformă pentru a primi sugestii personalizate."

        buyer_overview = {
            "message": buyer_message,
        }

    return render_template(
        "index.html",
        summary=summary,
        seller_overview=seller_overview,
        buyer_overview=buyer_overview,
        recommended_listings=recommended_listings,
    )


@main_bp.route("/admin/dashboard")
@role_required(User.ROLE_ADMIN)
def admin_dashboard():
    summary = get_market_summary()
    recent_evaluations = list_recent_evaluations(limit=10)
    recent_listings = list_recent_listings(limit=10)

    return render_template(
        "admin_dashboard.html",
        summary=summary,
        recent_evaluations=recent_evaluations,
        recent_listings=recent_listings,
    )


@main_bp.route("/admin/history")
@role_required(User.ROLE_ADMIN)
def admin_history():
    selected = {
        "brand": request.args.get("brand", "").strip(),
        "condition": request.args.get("condition", "").strip(),
        "date_from": request.args.get("date_from", "").strip(),
        "date_to": request.args.get("date_to", "").strip(),
    }

    rows = list_admin_evaluations(
        limit=100,
        brand=selected["brand"] or None,
        condition=selected["condition"] or None,
        date_from=selected["date_from"] or None,
        date_to=selected["date_to"] or None,
    )
    filters = get_admin_history_filters()

    return render_template(
        "admin_history.html",
        rows=rows,
        filters=filters,
        selected=selected,
    )


@main_bp.route("/favorites")
@role_required(User.ROLE_BUYER)
def favorites():
    rows = list_user_favorites(current_user.id)
    return render_template("favorites.html", rows=rows)


@main_bp.route("/favorites/add", methods=["POST"])
@role_required(User.ROLE_BUYER)
def add_to_favorites():
    listing_id = request.form.get("listing_id", "").strip()

    favorite, created = add_favorite(
        user_id=current_user.id,
        listing_id=listing_id,
    )

    if not favorite:
        flash("Anunțul nu a putut fi salvat la favorite.", "warning")
    elif created:
        refresh_seller_notifications_for_listing_segment(favorite.listing_id)
        flash("Anunțul a fost adăugat la favorite.", "success")
    else:
        flash("Acest anunț există deja la favorite.", "warning")

    return redirect(url_for("main.listings"))


@main_bp.route("/favorites/<int:favorite_id>/remove", methods=["POST"])
@role_required(User.ROLE_BUYER)
def remove_from_favorites(favorite_id):
    favorite_rows = list_user_favorites(current_user.id)
    favorite_row = next((row for row in favorite_rows if row["id"] == favorite_id), None)
    listing_id = favorite_row["listing_id"] if favorite_row else None

    ok = remove_favorite(favorite_id, current_user.id)

    if ok:
        if listing_id:
            refresh_seller_notifications_for_listing_segment(listing_id)
        flash("Favoritul a fost șters.", "success")
    else:
        flash("Favoritul nu a putut fi șters.", "warning")

    return redirect(url_for("main.favorites"))


@main_bp.route("/notifications")
@role_required(User.ROLE_SELLER)
def notifications():
    rows = list_user_notifications(current_user.id, limit=100)
    return render_template("notifications.html", rows=rows)


@main_bp.route("/notifications/<int:notification_id>/read", methods=["POST"])
@role_required(User.ROLE_SELLER)
def mark_notification_read(notification_id):
    ok = mark_notification_as_read(notification_id, current_user.id)

    if ok:
        flash("Notificarea a fost marcată ca citită.", "success")
    else:
        flash("Notificarea nu a putut fi actualizată.", "warning")

    return redirect(url_for("main.notifications"))


@main_bp.route("/notifications/read-all", methods=["POST"])
@role_required(User.ROLE_SELLER)
def mark_all_notifications_read_route():
    count = mark_all_notifications_as_read(current_user.id)

    if count > 0:
        flash(f"Au fost marcate ca citite {count} notificări.", "success")
    else:
        flash("Nu există notificări necitite.", "info")

    return redirect(url_for("main.notifications"))


@main_bp.route("/publish/<token>", methods=["POST"])
@role_required(User.ROLE_SELLER, User.ROLE_ADMIN)
def publish_listing(token):
    listing, already_exists, error_code = create_listing_from_evaluation(
        token,
        user_id=current_user.id,
        is_admin=current_user.is_admin,
    )

    if error_code == "forbidden":
        abort(403)

    if error_code == "not_found":
        abort(404)

    if not listing:
        abort(404)

    if already_exists:
        flash("Anunțul a fost deja publicat în platformă.", "warning")
    else:
        if listing.user and listing.user.is_seller:
            generate_seller_notifications_for_user(listing.user_id)
        flash("Anunțul a fost publicat cu succes în platformă.", "success")

    return redirect(url_for("main.listings"))


@main_bp.route("/evaluate", methods=["GET", "POST"])
def evaluate():
    filters = get_explore_filters()

    form_data = {
        "title": "",
        "description": "",
        "brand": "",
        "ram_gb": "",
        "model_family": "",
        "condition": "",
        "price_asked": "",
    }

    errors = {}

    if request.method == "POST":
        form_data = {
            "title": request.form.get("title", "").strip(),
            "description": request.form.get("description", "").strip(),
            "brand": request.form.get("brand", "").strip(),
            "ram_gb": request.form.get("ram_gb", "").strip(),
            "model_family": request.form.get("model_family", "").strip(),
            "condition": request.form.get("condition", "").strip(),
            "price_asked": request.form.get("price_asked", "").strip(),
        }

        errors = _validate_form(form_data, filters)

        if errors:
            flash("Formularul conține erori. Verifică câmpurile marcate.", "warning")
            return render_template(
                "evaluate.html",
                filters=filters,
                result=None,
                form_data=form_data,
                saved_token=None,
                saved_created_at=None,
                errors=errors,
                listing_already_published=False,
                can_publish=False,
                publish_block_reason=None,
                similar=[],
            )

        result = evaluate_listing(
            title=form_data["title"] or None,
            description=form_data["description"] or None,
            brand=form_data["brand"] or None,
            ram_gb=_to_int(form_data["ram_gb"]),
            model_family=form_data["model_family"] or None,
            condition=form_data["condition"] or None,
            price_asked=_to_float(form_data["price_asked"]),
        )

        saved, created_new = save_evaluation(
            input_payload=form_data,
            result_payload=result,
            user_id=current_user.id if current_user.is_authenticated else None,
        )

        if not created_new:
            flash("Această evaluare există deja în istoric. A fost reutilizată înregistrarea anterioară.", "warning")

        return redirect(url_for("main.result_page", token=saved.token))

    return render_template(
        "evaluate.html",
        filters=filters,
        result=None,
        form_data=form_data,
        saved_token=None,
        saved_created_at=None,
        errors=errors,
        listing_already_published=False,
        can_publish=False,
        publish_block_reason=None,
        similar=[],
    )


@main_bp.route("/result/<token>")
def result_page(token):
    saved = get_evaluation_by_token(token)
    if not saved:
        abort(404)

    form_input = saved.get("input") or {}
    result = saved.get("result") or {}
    result = _normalize_saved_result(result, form_input=form_input)
    result = _decorate_result_for_ui(result)

    filters = get_explore_filters()
    listing_already_published = is_listing_published(token)
    can_publish = can_user_publish_evaluation(token, current_user)

    publish_block_reason = None
    if current_user.is_authenticated and (current_user.is_seller or current_user.is_admin):
        if listing_already_published:
            publish_block_reason = "already_published"
        elif not can_publish:
            publish_block_reason = "forbidden"

    similar = get_similar_products(
        brand=form_input.get("brand"),
        ram_gb=_to_int(form_input.get("ram_gb")),
        model_family=form_input.get("model_family"),
        limit=4,
    )

    return render_template(
        "evaluate.html",
        filters=filters,
        result=result,
        form_data=form_input,
        saved_token=token,
        saved_created_at=saved["created_at"],
        errors={},
        listing_already_published=listing_already_published,
        can_publish=can_publish,
        publish_block_reason=publish_block_reason,
        similar=similar,
    )


@main_bp.route("/history")
@role_required(User.ROLE_SELLER, User.ROLE_BUYER, User.ROLE_ADMIN)
def history():
    rows = list_user_evaluations(current_user.id, limit=30)
    return render_template("history.html", rows=rows)


@main_bp.route("/listings")
def listings():
    rows = list_recent_listings(limit=30)

    favorite_listing_ids = set()
    if current_user.is_authenticated and current_user.is_buyer:
        favorite_listing_ids = build_favorite_listing_ids(current_user.id)

    return render_template(
        "listings.html",
        rows=rows,
        favorite_listing_ids=favorite_listing_ids,
    )


@main_bp.route("/explore")
def explore():
    filters = get_explore_filters()

    selected = {
        "brand": request.args.get("brand", "").strip(),
        "family": request.args.get("family", "").strip(),
        "ram": request.args.get("ram", "").strip(),
        "condition": request.args.get("condition", "").strip(),
        "source": request.args.get("source", "").strip(),
    }

    data = get_explore_products(
        brand=selected["brand"] or None,
        family=selected["family"] or None,
        ram=_to_int(selected["ram"]),
        condition=selected["condition"] or None,
        source=selected["source"] or None,
        limit=60,
    )

    return render_template(
        "explore.html",
        filters=filters,
        selected=selected,
        data=data,
    )


@main_bp.route("/profile")
@role_required(User.ROLE_SELLER)
def profile():
    evaluations = list_user_evaluations(current_user.id, limit=20)
    listings = list_user_listings(current_user.id, limit=20)
    return render_template(
        "profile.html",
        evaluations=evaluations,
        listings=listings,
    )