import json
import uuid

from app import db
from app.models import EvaluationResult, Listing


def save_evaluation(input_payload, result_payload):
    token = uuid.uuid4().hex[:16]

    row = EvaluationResult(
        token=token,
        input_json=json.dumps(input_payload, ensure_ascii=False),
        result_json=json.dumps(result_payload, ensure_ascii=False),
    )
    db.session.add(row)
    db.session.commit()

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

        items.append({
            "token": row.token,
            "created_at": row.created_at,
            "title": input_data.get("title"),
            "brand": input_data.get("brand"),
            "model_family": input_data.get("model_family"),
            "condition": input_data.get("condition"),
            "price_asked": input_data.get("price_asked"),
            "fair_price_used": (
                result_data.get("price_estimation", {})
                .get("outputs", {})
                .get("fair_price_used")
            ),
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


def create_listing_from_evaluation(token):
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