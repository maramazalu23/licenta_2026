import json
import uuid
from datetime import datetime, time, timezone

from app import db
from app.models import EvaluationResult, Listing, User, Favorite, Notification
from app.db_market import get_explore_filters, get_price_stats


def utc_now():
    return datetime.now(timezone.utc)


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


def _extract_listing_metrics_from_saved(saved):
    if not saved:
        return None, None

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

    return recommended_price, deal_score


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
        "user_email": row.user.email if row.user is not None else None,
    }


def _segment_label(brand=None, model_family=None, ram_gb=None):
    parts = []
    if brand:
        parts.append(str(brand))
    if model_family:
        parts.append(str(model_family))
    if ram_gb:
        parts.append(f"{ram_gb} GB RAM")
    return " / ".join(parts) if parts else "segment necunoscut"


def _market_median_for_listing(brand=None, model_family=None, ram_gb=None, condition=None):
    stats = get_price_stats(
        brand=brand,
        ram_gb=ram_gb,
        model_family=model_family,
    )

    if condition == "new":
        median = (stats.get("new") or {}).get("median")
        if median is not None:
            return median
        return (stats.get("used") or {}).get("median")

    median = (stats.get("used") or {}).get("median")
    if median is not None:
        return median
    return (stats.get("new") or {}).get("median")


def _notification_to_item(row):
    return {
        "id": row.id,
        "type": row.type,
        "title": row.title,
        "message": row.message,
        "brand": row.brand,
        "model_family": row.model_family,
        "ram_gb": row.ram_gb,
        "is_read": row.is_read,
        "created_at": row.created_at,
        "read_at": row.read_at,
    }


def _listing_to_favorite_item(row):
    return {
        "id": row.id,
        "listing_id": row.listing_id,
        "created_at": row.created_at,
        "title": row.listing.title if row.listing else None,
        "brand": row.listing.brand if row.listing else None,
        "model_family": row.listing.model_family if row.listing else None,
        "ram_gb": row.listing.ram_gb if row.listing else None,
        "price_asked": row.listing.price_asked if row.listing else None,
        "condition": row.listing.condition if row.listing else None,
        "recommended_price": row.listing.recommended_price if row.listing else None,
        "deal_score": row.listing.deal_score if row.listing else None,
        "listing_created_at": row.listing.created_at if row.listing else None,
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


def can_user_publish_evaluation(token, user):
    if not token or user is None or not getattr(user, "is_authenticated", False):
        return False

    if not (user.is_seller or user.is_admin):
        return False

    row = EvaluationResult.query.filter_by(token=token).first()
    if not row:
        return False

    if user.is_admin:
        return True

    return row.user_id == user.id


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

    rows = query.all()

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

    return items[:limit]


def get_admin_history_filters():
    market_filters = get_explore_filters()
    return {
        "brands": market_filters.get("brands", []),
        "conditions": ["used", "new"],
    }


def create_listing_from_evaluation(token, user_id=None, is_admin=False):
    if not token or not user_id:
        return None, False, "invalid"

    evaluation_row = EvaluationResult.query.filter_by(token=token).first()
    if not evaluation_row:
        return None, False, "not_found"

    if not is_admin and evaluation_row.user_id != user_id:
        return None, False, "forbidden"

    existing = Listing.query.filter_by(evaluation_token=token).first()
    if existing:
        return existing, True, None

    saved = {
        "id": evaluation_row.id,
        "token": evaluation_row.token,
        "created_at": evaluation_row.created_at,
        "input": json.loads(evaluation_row.input_json),
        "result": json.loads(evaluation_row.result_json),
    }

    input_data = saved["input"]
    recommended_price, deal_score = _extract_listing_metrics_from_saved(saved)

    owner_id = evaluation_row.user_id or user_id
    if not owner_id:
        return None, False, "forbidden"

    listing = Listing(
        title=input_data.get("title") or "Anunț fără titlu",
        brand=input_data.get("brand"),
        model_family=input_data.get("model_family"),
        ram_gb=_safe_int(input_data.get("ram_gb")),
        price_asked=_safe_float(input_data.get("price_asked")) or 0.0,
        condition=input_data.get("condition"),
        description=input_data.get("description"),
        recommended_price=_safe_float(recommended_price),
        deal_score=_safe_float(deal_score),
        evaluation_token=token,
        user_id=owner_id,
    )

    db.session.add(listing)
    db.session.commit()
    return listing, False, None


def refresh_seller_notifications_for_listing_segment(listing_id):
    listing_id = _safe_int(listing_id)
    if not listing_id:
        return 0

    listing = Listing.query.filter_by(id=listing_id).first()
    if not listing or not listing.brand:
        return 0

    segment_listings = (
        Listing.query
        .filter_by(
            brand=listing.brand,
            model_family=listing.model_family,
            ram_gb=listing.ram_gb,
        )
        .all()
    )

    seller_ids = {
        row.user_id
        for row in segment_listings
        if row.user_id and row.user and row.user.is_seller
    }

    updated = 0
    for seller_id in seller_ids:
        updated += generate_seller_notifications_for_user(seller_id)

    return updated


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
            "model_family": row.model_family,
            "ram_gb": row.ram_gb,
            "price_asked": row.price_asked,
            "condition": row.condition,
            "description": row.description,
            "evaluation_token": row.evaluation_token,
            "created_at": row.created_at,
            "recommended_price": row.recommended_price,
            "deal_score": row.deal_score,
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
            "recommended_price": row.recommended_price,
            "deal_score": row.deal_score,
        })

    return items


def list_user_favorites(user_id):
    rows = (
        Favorite.query
        .filter_by(user_id=user_id)
        .order_by(Favorite.created_at.desc())
        .all()
    )

    return [_listing_to_favorite_item(row) for row in rows]


def add_favorite(user_id, listing_id):
    listing_id = _safe_int(listing_id)

    if not user_id or not listing_id:
        return None, False

    listing = Listing.query.filter_by(id=listing_id).first()
    if not listing:
        return None, False

    existing = (
        Favorite.query
        .filter_by(
            user_id=user_id,
            listing_id=listing_id,
        )
        .first()
    )
    if existing:
        return existing, False

    row = Favorite(
        user_id=user_id,
        listing_id=listing_id,
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


def build_favorite_listing_ids(user_id):
    rows = (
        Favorite.query
        .filter_by(user_id=user_id)
        .all()
    )

    return {row.listing_id for row in rows}


def generate_seller_notifications_for_user(user_id):
    seller = User.query.filter_by(id=user_id, role=User.ROLE_SELLER).first()
    if not seller:
        return 0

    listings = (
        Listing.query
        .filter_by(user_id=user_id)
        .order_by(Listing.created_at.desc())
        .all()
    )

    created_or_updated = 0
    seen_segments = set()
    active_segments = set()

    for listing in listings:
        segment_key = (listing.brand or "", listing.model_family or "", listing.ram_gb)
        if segment_key in seen_segments:
            continue
        seen_segments.add(segment_key)

        if not listing.brand:
            continue

        active_segments.add(segment_key)

        matching_listing_ids = {
            row.id
            for row in Listing.query.filter_by(
                brand=listing.brand,
                model_family=listing.model_family,
                ram_gb=listing.ram_gb,
            ).all()
        }

        if not matching_listing_ids:
            continue

        matching_favorites = (
            Favorite.query
            .filter(Favorite.listing_id.in_(matching_listing_ids))
            .all()
        )

        buyer_ids = sorted({fav.user_id for fav in matching_favorites if fav.user_id != user_id})
        buyers_count = len(buyer_ids)

        latest = (
            Notification.query
            .filter_by(
                user_id=user_id,
                type="favorite_match",
                brand=listing.brand,
                model_family=listing.model_family,
                ram_gb=listing.ram_gb,
            )
            .order_by(Notification.created_at.desc())
            .first()
        )

        if buyers_count <= 0:
            if latest:
                db.session.delete(latest)
                created_or_updated += 1
            continue

        market_median = _market_median_for_listing(
            brand=listing.brand,
            model_family=listing.model_family,
            ram_gb=listing.ram_gb,
            condition=listing.condition,
        )

        segment_label = _segment_label(
            brand=listing.brand,
            model_family=listing.model_family,
            ram_gb=listing.ram_gb,
        )

        title = f"Interes detectat pentru {segment_label}"
        buyer_phrase = "cumpărător a" if buyers_count == 1 else "cumpărători au"

        if market_median is not None:
            message = (
                f"{buyers_count} {buyer_phrase} salvat la favorite anunțuri din segmentul {segment_label}. "
                f"Prețul median estimat din piață pentru acest segment este {market_median:.0f} RON."
            )
        else:
            message = (
                f"{buyers_count} {buyer_phrase} salvat la favorite anunțuri din segmentul {segment_label}. "
                f"Nu există momentan o mediană de piață suficient de clară pentru acest segment."
            )

        if latest and latest.message == message and latest.title == title:
            continue

        if latest:
            latest.title = title
            latest.message = message
            latest.created_at = utc_now()
            latest.is_read = False
            latest.read_at = None
            created_or_updated += 1
            continue

        row = Notification(
            user_id=user_id,
            type="favorite_match",
            title=title,
            message=message,
            brand=listing.brand,
            model_family=listing.model_family,
            ram_gb=listing.ram_gb,
            is_read=False,
        )
        db.session.add(row)
        created_or_updated += 1

    stale_notifications = (
        Notification.query
        .filter_by(user_id=user_id, type="favorite_match")
        .all()
    )

    for row in stale_notifications:
        row_key = (row.brand or "", row.model_family or "", row.ram_gb)
        if row_key not in active_segments:
            db.session.delete(row)
            created_or_updated += 1

    if created_or_updated:
        db.session.commit()

    return created_or_updated


def list_user_notifications(user_id, limit=50):
    rows = (
        Notification.query
        .filter_by(user_id=user_id)
        .order_by(Notification.is_read.asc(), Notification.created_at.desc())
        .limit(limit)
        .all()
    )
    return [_notification_to_item(row) for row in rows]


def count_unread_notifications(user_id):
    return (
        Notification.query
        .filter_by(user_id=user_id, is_read=False)
        .count()
    )


def mark_notification_as_read(notification_id, user_id):
    row = (
        Notification.query
        .filter_by(id=notification_id, user_id=user_id)
        .first()
    )
    if not row:
        return False

    if not row.is_read:
        row.is_read = True
        row.read_at = utc_now()
        db.session.commit()

    return True


def mark_all_notifications_as_read(user_id):
    rows = (
        Notification.query
        .filter_by(user_id=user_id, is_read=False)
        .all()
    )

    if not rows:
        return 0

    now = utc_now()
    for row in rows:
        row.is_read = True
        row.read_at = now

    db.session.commit()
    return len(rows)


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