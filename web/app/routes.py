from flask import Blueprint, render_template, request, redirect, url_for, abort

from app.scoring.service import evaluate_listing
from app.db_market import (
    get_market_summary,
    get_explore_filters,
    get_explore_products,
)
from app.services import save_evaluation, get_evaluation_by_token


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


def _decorate_result_for_ui(result):
    result["ui"] = {
        "deal_label_ro": _deal_label_ro(result["price_estimation"]["outputs"]["deal_rating_label"]),
        "depreciation_label_ro": _depreciation_label_ro(result["depreciation"]["label"]),
        "attractiveness_label_ro": _attractiveness_label_ro(result["attractiveness"]["label"]),
        "deal_badge_class": _score_badge_class(result["price_estimation"]["outputs"]["deal_rating_score"]),
        "depreciation_badge_class": _score_badge_class(result["depreciation"]["score"]),
        "attractiveness_badge_class": _score_badge_class(result["attractiveness"]["score"]),
    }
    return result


@main_bp.route("/")
def index():
    summary = get_market_summary()
    return render_template("index.html", summary=summary)


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

    result = saved["result"]
    result = _decorate_result_for_ui(result)

    form_input = saved["input"]
    filters = get_explore_filters()

    return render_template(
        "evaluate.html",
        filters=filters,
        result=result,
        form_data=form_input,
        saved_token=token,
        saved_created_at=saved["created_at"],
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