from flask import Blueprint, render_template, request, redirect, url_for, abort, flash

from app.scoring.service import evaluate_listing
from app.db_market import (
    get_market_summary,
    get_explore_filters,
    get_explore_products,
)
from app.services import (
    save_evaluation,
    get_evaluation_by_token,
    list_recent_evaluations,
    create_listing_from_evaluation,
    list_recent_listings,
)


main_bp = Blueprint("main", __name__)


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


def _normalize_saved_result(result, form_input=None):
    """
    Compatibilitate pentru evaluari vechi salvate in DB.
    Daca lipsesc noile chei (ex. outputs.fair_price), le completam din schema veche.
    """
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
    summary = get_market_summary()
    return render_template("index.html", summary=summary)


@main_bp.route("/publish/<token>", methods=["POST"])
def publish_listing(token):
    listing, already_exists = create_listing_from_evaluation(token)
    if not listing:
        abort(404)

    if already_exists:
        flash("Anunțul a fost deja publicat în platformă.", "warning")
    else:
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

        result = evaluate_listing(
            title=form_data["title"] or None,
            description=form_data["description"] or None,
            brand=form_data["brand"] or None,
            ram_gb=_to_int(form_data["ram_gb"]),
            model_family=form_data["model_family"] or None,
            condition=form_data["condition"] or None,
            price_asked=_to_float(form_data["price_asked"]),
        )

        result = _decorate_result_for_ui(result)

        saved = save_evaluation(
            input_payload=form_data,
            result_payload=result,
        )

        return redirect(url_for("main.result_page", token=saved.token))

    return render_template(
        "evaluate.html",
        filters=filters,
        result=None,
        form_data=form_data,
        saved_token=None,
        saved_created_at=None,
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

    return render_template(
        "evaluate.html",
        filters=filters,
        result=result,
        form_data=form_input,
        saved_token=token,
        saved_created_at=saved["created_at"],
    )


@main_bp.route("/history")
def history():
    rows = list_recent_evaluations(limit=30)
    return render_template("history.html", rows=rows)


@main_bp.route("/listings")
def listings():
    rows = list_recent_listings(limit=30)
    return render_template("listings.html", rows=rows)


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