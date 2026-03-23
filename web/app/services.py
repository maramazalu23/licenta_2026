import json
import uuid

from app import db
from app.models import EvaluationResult, Listing


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


def save_evaluation(input_payload, result_payload, user_id=None):
    normalized_input = _canonical_input_payload(input_payload)

    query = EvaluationResult.query

    if user_id is None:
        query = query.filter(EvaluationResult.user_id.is_(None))
    else:
        query = query.filter_by(user_id=user_id)

    existing_rows = (
        query
        .order_by(EvaluationResult.created_at.desc())
        .all()
    )

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

    items = []
    for row in rows:
        input_data = json.loads(row.input_json)
        result_data = json.loads(row.result_json)

        condition = input_data.get("condition")
        recommended_price = _extract_recommended_price(result_data, condition)

        items.append({
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
        })

    return items


def create_listing_from_evaluation(token, user_id=None):
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
    

def list_user_evaluations(user_id, limit=20):
    rows = (
        EvaluationResult.query
        .filter_by(user_id=user_id)
        .order_by(EvaluationResult.created_at.desc())
        .limit(limit)
        .all()
    )

    items = []
    for row in rows:
        input_data = json.loads(row.input_json)
        result_data = json.loads(row.result_json)

        condition = input_data.get("condition")
        recommended_price = _extract_recommended_price(result_data, condition)

        items.append({
            "token": row.token,
            "created_at": row.created_at,
            "title": input_data.get("title"),
            "brand": input_data.get("brand"),
            "model_family": input_data.get("model_family"),
            "condition": condition,
            "price_asked": input_data.get("price_asked"),
            "recommended_price": recommended_price,
            "deal_score": (
                result_data.get("price_estimation", {})
                .get("outputs", {})
                .get("deal_rating_score")
            ),
            "attractiveness_score": (
                result_data.get("attractiveness", {})
                .get("score")
            ),
        })

    return items


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