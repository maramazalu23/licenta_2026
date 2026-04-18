import json
import uuid
from datetime import datetime, time

from app import db
from app.models import EvaluationResult, Listing, User, Favorite


def _normalize_text(value):
    if value is None:
        return ""
    return " ".join(str(value).strip().split())


def _normalize_condition(value):
    value = str(value).strip().lower() if value is not None else ""
    return value if value in {"used", "new"} else ""


def _normalize_price(value):
    if value is None or value == "":
        return ""
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return ""


def _normalize_ram(value):
    if value is None or value == "":
        return ""
    try:
        return str(int(float(value)))
    except (TypeError, ValueError):
        return ""


def _canonical_input_payload(input_payload):
    return {
        "title": _normalize_text(input_payload.get("title")),
        "description": _normalize_text(input_payload.get("description")),
        "brand": _normalize_text(input_payload.get("brand")),
        "ram_gb": _normalize_ram(input_payload.get("ram_gb")),
        "model_family": _normalize_text(input_payload.get("model_family")),
        "condition": _normalize_condition(input_payload.get("condition")),
        "price_asked": _normalize_price(input_payload.get("price_asked")),
    }


def _same_evaluation_input(left_payload, right_payload):
    return _canonical_input_payload(left_payload) == _canonical_input_payload(right_payload)


def _safe_int(value):
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _safe_float(value):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_datetime_start(value):
    if not value:
        return None
    try:
        return datetime.combine(datetime.strptime(value, "%Y-%m-%d").date(), time.min)
    except ValueError:
        return None


def _safe_datetime_end(value):
    if not value:
        return None
    try:
        return datetime.combine(datetime.strptime(value, "%Y-%m-%d").date(), time.max)
    except ValueError:
        return None


def _row_to_evaluation_item(row):
    input_data = json.loads(row.input_json)
    result_data = json.loads(row.result_json)

    condition = input_data.get("condition")
    recommended_price = _extract_recommended_price(result_data, condition)

    return {
        "token": row.token,
        "created_at": row.created_at,
        "title": input_data.get("title"),
        "brand": input_data.get("brand"),
        "model_family": input_data.get("model_family"),
        "condition": condition,
        "price_asked": input_data.get("price_asked"),
        "recommended_price": recommended_price,
        "deal_label": (
            result_data.get("price_estimation", {})
            .get("outputs", {})
            .get("deal_rating_label")
        ),
        "deal_score": (
            result_data.get("price_estimation", {})
            .get("outputs", {})
            .get("deal_rating_score")
        ),
        "attractiveness_score": (
            result_data.get("attractiveness", {})
            .get("score")
        ),
        "user_id": row.user_id,
        "user_email": row.user.email if getattr(row, "user", None) else None,
    }


def save_evaluation(input_payload, result_payload, user_id=None):
    normalized_input = _canonical_input_payload(input_payload)

    query = EvaluationResult.query

    if user_id is None:
        query = query.filter(EvaluationResult.user_id.is_(None))
    else:
        query = query.filter_by(user_id=user_id)

    existing_rows = query.order_by(EvaluationResult.created_at.desc()).all()

    for existing in existing_rows:
        try:
            existing_input = json.loads(existing.input_json)
        except Exception:
            continue

        if _same_evaluation_input(existing_input, normalized_input):
            return existing, False

    token = uuid.uuid4().hex[:16]

    row = EvaluationResult(
        token=token,
        input_json=json.dumps(normalized_input, ensure_ascii=False),
        result_json=json.dumps(result_payload, ensure_ascii=False),
        user_id=user_id,
    )
    db.session.add(row)
    db.session.commit()

    return row, True


def claim_evaluation_for_user(token, user_id):
    if not token or not user_id:
        return None

    row = EvaluationResult.query.filter_by(token=token).first()
    if not row:
        return None

    if row.user_id == user_id:
        return row

    if row.user_id is None:
        row.user_id = user_id
        db.session.commit()
        return row

    return row


def get_evaluation_by_token(token):
    row = EvaluationResult.query.filter_by(token=token).first()
    if not row:
        return None

    return {
        "id": row.id,
        "token": row.token,
        "created_at": row.created_at,
        "input": json.loads(row.input_json),
        "result": json.loads(row.result_json),
    }


def is_listing_published(token):
    if not token:
        return False
    return Listing.query.filter_by(evaluation_token=token).first() is not None


def _extract_recommended_price(result_data, condition):
    outputs = result_data.get("price_estimation", {}).get("outputs", {})

    fair_price = outputs.get("fair_price")
    fair_price_used = outputs.get("fair_price_used")
    fair_price_new = outputs.get("fair_price_new")

    if fair_price is not None:
        return fair_price

    if condition == "new" and fair_price_new is not None:
        return fair_price_new

    return fair_price_used


def list_recent_evaluations(limit=20):
    rows = (
        EvaluationResult.query
        .order_by(EvaluationResult.created_at.desc())
        .limit(limit)
        .all()
    )

    return [_row_to_evaluation_item(row) for row in rows]


def list_admin_evaluations(
    limit=50,
    brand=None,
    condition=None,
    date_from=None,
    date_to=None,
):
    query = EvaluationResult.query.order_by(EvaluationResult.created_at.desc())

    dt_from = _safe_datetime_start(date_from)
    dt_to = _safe_datetime_end(date_to)

    if dt_from is not None:
        query = query.filter(EvaluationResult.created_at >= dt_from)

    if dt_to is not None:
        query = query.filter(EvaluationResult.created_at <= dt_to)

    rows = query.limit(limit).all()

    items = []
    brand_norm = _normalize_text(brand).lower()
    condition_norm = _normalize_condition(condition)

    for row in rows:
        item = _row_to_evaluation_item(row)

        item_brand = (item.get("brand") or "").strip().lower()
        item_condition = _normalize_condition(item.get("condition"))

        if brand_norm and item_brand != brand_norm:
            continue

        if condition_norm and item_condition != condition_norm:
            continue

        items.append(item)

    return items


def get_admin_history_filters():
    rows = (
        EvaluationResult.query
        .order_by(EvaluationResult.created_at.desc())
        .all()
    )

    brands = set()

    for row in rows:
        try:
            input_data = json.loads(row.input_json)
        except Exception:
            continue

        brand = _normalize_text(input_data.get("brand"))
        if brand:
            brands.add(brand)

    return {
        "brands": sorted(brands),
        "conditions": ["used", "new"],
    }


def create_listing_from_evaluation(token, user_id=None):
    if not user_id:
        return None, False

    saved = get_evaluation_by_token(token)
    if not saved:
        return None, False

    existing = Listing.query.filter_by(evaluation_token=token).first()
    if existing:
        return existing, True

    input_data = saved["input"]

    listing = Listing(
        title=input_data.get("title") or "Anunț fără titlu",
        brand=input_data.get("brand"),
        model_family=input_data.get("model_family"),
        ram_gb=_safe_int(input_data.get("ram_gb")),
        price_asked=_safe_float(input_data.get("price_asked")) or 0.0,
        condition=input_data.get("condition"),
        description=input_data.get("description"),
        evaluation_token=token,
        user_id=user_id,
    )

    db.session.add(listing)
    db.session.commit()
    return listing, False


def list_recent_listings(limit=30):
    rows = (
        Listing.query
        .order_by(Listing.created_at.desc())
        .limit(limit)
        .all()
    )

    items = []
    for row in rows:
        recommended_price = None
        deal_score = None

        if row.evaluation_token:
            saved = get_evaluation_by_token(row.evaluation_token)
            if saved:
                input_data = saved.get("input", {})
                result_data = saved.get("result", {})
                recommended_price = _extract_recommended_price(
                    result_data,
                    input_data.get("condition"),
                )
                deal_score = (
                    result_data.get("price_estimation", {})
                    .get("outputs", {})
                    .get("deal_rating_score")
                )

        items.append({
            "id": row.id,
            "title": row.title,
            "brand": row.brand,
            "model_family": row.model_family,
            "ram_gb": row.ram_gb,
            "price_asked": row.price_asked,
            "condition": row.condition,
            "description": row.description,
            "evaluation_token": row.evaluation_token,
            "created_at": row.created_at,
            "recommended_price": recommended_price,
            "deal_score": deal_score,
        })

    return items


def list_user_evaluations(user_id, limit=20):
    rows = (
        EvaluationResult.query
        .filter_by(user_id=user_id)
        .order_by(EvaluationResult.created_at.desc())
        .limit(limit)
        .all()
    )

    return [_row_to_evaluation_item(row) for row in rows]


def list_user_listings(user_id, limit=20):
    rows = (
        Listing.query
        .filter_by(user_id=user_id)
        .order_by(Listing.created_at.desc())
        .limit(limit)
        .all()
    )

    items = []
    for row in rows:
        recommended_price = None
        deal_score = None

        if row.evaluation_token:
            saved = get_evaluation_by_token(row.evaluation_token)
            if saved:
                input_data = saved.get("input", {})
                result_data = saved.get("result", {})
                recommended_price = _extract_recommended_price(
                    result_data,
                    input_data.get("condition"),
                )
                deal_score = (
                    result_data.get("price_estimation", {})
                    .get("outputs", {})
                    .get("deal_rating_score")
                )

        items.append({
            "id": row.id,
            "title": row.title,
            "brand": row.brand,
            "model_family": row.model_family,
            "ram_gb": row.ram_gb,
            "price_asked": row.price_asked,
            "condition": row.condition,
            "description": row.description,
            "evaluation_token": row.evaluation_token,
            "created_at": row.created_at,
            "recommended_price": recommended_price,
            "deal_score": deal_score,
        })

    return items


def list_user_favorites(user_id):
    rows = (
        Favorite.query
        .filter_by(user_id=user_id)
        .order_by(Favorite.created_at.desc())
        .all()
    )

    items = []
    for row in rows:
        items.append({
            "id": row.id,
            "brand": row.brand,
            "model_family": row.model_family,
            "ram_gb": row.ram_gb,
            "created_at": row.created_at,
        })

    return items


def favorite_exists(user_id, brand, model_family=None, ram_gb=None):
    return (
        Favorite.query
        .filter_by(
            user_id=user_id,
            brand=brand,
            model_family=model_family,
            ram_gb=ram_gb,
        )
        .first()
        is not None
    )


def add_favorite(user_id, brand, model_family=None, ram_gb=None):
    brand = _normalize_text(brand)
    model_family = _normalize_text(model_family) or None
    ram_gb = _safe_int(ram_gb)

    if not user_id or not brand:
        return None, False

    existing = (
        Favorite.query
        .filter_by(
            user_id=user_id,
            brand=brand,
            model_family=model_family,
            ram_gb=ram_gb,
        )
        .first()
    )
    if existing:
        return existing, False

    row = Favorite(
        user_id=user_id,
        brand=brand,
        model_family=model_family,
        ram_gb=ram_gb,
    )
    db.session.add(row)
    db.session.commit()
    return row, True


def remove_favorite(favorite_id, user_id):
    if not favorite_id or not user_id:
        return False

    row = Favorite.query.filter_by(id=favorite_id, user_id=user_id).first()
    if not row:
        return False

    db.session.delete(row)
    db.session.commit()
    return True


def build_favorite_keys(user_id):
    rows = (
        Favorite.query
        .filter_by(user_id=user_id)
        .all()
    )

    keys = set()
    for row in rows:
        keys.add((row.brand or "", row.model_family or "", row.ram_gb))
    return keys


def set_user_role(email, role):
    email = (email or "").strip().lower()
    role = (role or "").strip().lower()

    if not email or role not in {User.ROLE_ADMIN, User.ROLE_SELLER, User.ROLE_BUYER}:
        return None, False

    user = User.query.filter_by(email=email).first()
    if not user:
        return None, False

    if user.role == role:
        return user, False

    user.role = role
    db.session.commit()
    return user, True