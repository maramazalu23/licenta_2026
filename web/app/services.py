import json
import uuid
from datetime import datetime, time

from app import db
from app.models import EvaluationResult, Listing, User, Favorite, Notification, utc_now
from sqlalchemy import and_, or_, func
from app.db_market import get_explore_filters, get_price_stats


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
        try:
            input_data = json.loads(row.input_json)
            result_data = json.loads(row.result_json)
        except Exception:
            continue

        item_brand = _normalize_text(input_data.get("brand")).lower()
        item_condition = _normalize_condition(input_data.get("condition"))

        if brand_norm and item_brand != brand_norm:
            continue

        if condition_norm and item_condition != condition_norm:
            continue

        recommended_price = _extract_recommended_price(result_data, item_condition)

        items.append({
            "token": row.token,
            "created_at": row.created_at,
            "title": input_data.get("title"),
            "brand": input_data.get("brand"),
            "model_family": input_data.get("model_family"),
            "condition": item_condition,
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
        })

        if len(items) >= limit:
            break

    return items


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
        condition=_normalize_condition(input_data.get("condition")),
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
            "user_id": row.user_id,
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


def list_recommended_listings_for_buyer(user_id, limit=6):
    if not user_id:
        return []

    favorite_rows = (
        Favorite.query
        .filter_by(user_id=user_id)
        .all()
    )

    if not favorite_rows:
        return []

    favorite_listing_ids = {row.listing_id for row in favorite_rows}

    segment_scores = {}
    for row in favorite_rows:
        listing = row.listing
        if not listing:
            continue

        key = (
            (listing.brand or "").strip(),
            (listing.model_family or "").strip(),
            listing.ram_gb,
        )

        if not key[0]:
            continue

        segment_scores[key] = segment_scores.get(key, 0) + 1

    if not segment_scores:
        return []

    candidate_scores = {}

    for (brand, model_family, ram_gb), freq in segment_scores.items():
        base_query = Listing.query.filter(Listing.id.notin_(favorite_listing_ids))

        priority_filters = []

        if brand and model_family and ram_gb is not None:
            priority_filters.append((
                4,
                and_(
                    Listing.brand == brand,
                    Listing.model_family == model_family,
                    Listing.ram_gb == ram_gb,
                )
            ))

        if brand and model_family:
            priority_filters.append((
                3,
                and_(
                    Listing.brand == brand,
                    Listing.model_family == model_family,
                )
            ))

        if brand and ram_gb is not None:
            priority_filters.append((
                2,
                and_(
                    Listing.brand == brand,
                    Listing.ram_gb == ram_gb,
                )
            ))

        if brand:
            priority_filters.append((
                1,
                Listing.brand == brand
            ))

        for priority, filter_expr in priority_filters:
            rows = (
                base_query
                .filter(filter_expr)
                .order_by(Listing.created_at.desc())
                .limit(30)
                .all()
            )

            for row in rows:
                score = priority * 10

                if brand and row.brand == brand:
                    score += 3
                if model_family and row.model_family == model_family:
                    score += 2
                if ram_gb is not None and row.ram_gb == ram_gb:
                    score += 1

                score *= freq

                current = candidate_scores.get(row.id)
                if current is None or score > current["score"]:
                    candidate_scores[row.id] = {
                        "score": score,
                        "row": row,
                    }

    ranked = sorted(
        candidate_scores.values(),
        key=lambda item: (item["score"], item["row"].created_at or utc_now()),
        reverse=True,
    )

    items = []
    for item in ranked[:limit]:
        row = item["row"]
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
            "match_score": item["score"],
        })

    return items


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


# utilitar administrativ pentru schimbarea rolurilor din shell / scripturi interne
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


def delete_listing(listing_id, user_id=None, is_admin=False):
    listing_id = _safe_int(listing_id)
    user_id = _safe_int(user_id)

    if not listing_id:
        return False, "invalid"

    row = Listing.query.filter_by(id=listing_id).first()
    if not row:
        return False, "not_found"

    if not is_admin:
        if not user_id or row.user_id != user_id:
            return False, "forbidden"

    segment_brand = row.brand
    segment_family = row.model_family
    segment_ram = row.ram_gb

    db.session.delete(row)
    db.session.commit()

    if segment_brand:
        affected = Listing.query.filter_by(
            brand=segment_brand,
            model_family=segment_family,
            ram_gb=segment_ram,
        ).all()
        seller_ids = {
            r.user_id
            for r in affected
            if r.user_id and r.user and r.user.is_seller
        }
        for sid in seller_ids:
            generate_seller_notifications_for_user(sid)

    return True, None


def get_admin_dashboard_metrics():
    return {
        "users_total": User.query.count(),
        "buyers_total": User.query.filter_by(role=User.ROLE_BUYER).count(),
        "sellers_total": User.query.filter_by(role=User.ROLE_SELLER).count(),
        "admins_total": User.query.filter_by(role=User.ROLE_ADMIN).count(),
        "evaluations_total": EvaluationResult.query.count(),
        "listings_total": Listing.query.count(),
        "favorites_total": Favorite.query.count(),
        "notifications_total": Notification.query.count(),
    }


def _get_evaluations_per_day(days=30):
    from datetime import timedelta

    rows = (
        db.session.query(
            func.date(EvaluationResult.created_at).label("day"),
            func.count(EvaluationResult.id).label("count"),
        )
        .group_by(func.date(EvaluationResult.created_at))
        .order_by(func.date(EvaluationResult.created_at).asc())
        .all()
    )

    counts_by_day = {}
    for row in rows:
        day_str = str(row.day)
        counts_by_day[day_str] = int(row.count)

    today = utc_now().date()
    labels = []
    values = []

    for i in range(days - 1, -1, -1):
        d = today - timedelta(days=i)
        d_str = d.strftime("%Y-%m-%d")
        labels.append(d_str)
        values.append(counts_by_day.get(d_str, 0))

    return {"labels": labels, "values": values}


def _get_evaluations_per_brand(limit=10):
    rows = (
        EvaluationResult.query
        .order_by(EvaluationResult.created_at.desc())
        .all()
    )

    counts = {}
    for row in rows:
        try:
            input_data = json.loads(row.input_json)
        except Exception:
            continue

        brand = (input_data.get("brand") or "").strip()
        if not brand:
            continue

        counts[brand] = counts.get(brand, 0) + 1

    ranked = sorted(counts.items(), key=lambda item: item[1], reverse=True)[:limit]

    return {
        "labels": [brand for brand, _ in ranked],
        "values": [count for _, count in ranked],
    }


def _get_price_comparison_per_brand(limit=8):
    rows = Listing.query.all()

    grouped = {}
    for row in rows:
        brand = (row.brand or "").strip()
        if not brand:
            continue

        bucket = grouped.setdefault(
            brand,
            {
                "count": 0,
                "sum_asked": 0.0,
                "sum_recommended": 0.0,
                "asked_n": 0,
                "recommended_n": 0,
            }
        )

        bucket["count"] += 1

        if row.price_asked is not None and float(row.price_asked) > 0:
            bucket["sum_asked"] += float(row.price_asked)
            bucket["asked_n"] += 1

        # Excludem 0 și None din prețul recomandat — distorsionează media
        if row.recommended_price is not None and float(row.recommended_price) > 0:
            bucket["sum_recommended"] += float(row.recommended_price)
            bucket["recommended_n"] += 1

    ranked = sorted(
        grouped.items(),
        key=lambda item: item[1]["count"],
        reverse=True,
    )[:limit]

    labels = []
    asked_values = []
    recommended_values = []

    for brand, data in ranked:
        labels.append(brand)
        asked_avg = round(data["sum_asked"] / data["asked_n"], 2) if data["asked_n"] else None
        recommended_avg = round(data["sum_recommended"] / data["recommended_n"], 2) if data["recommended_n"] else None
        asked_values.append(asked_avg)
        recommended_values.append(recommended_avg)

    return {
        "labels": labels,
        "asked_values": asked_values,
        "recommended_values": recommended_values,
    }


def _get_condition_distribution_platform():
    used_count = Listing.query.filter_by(condition="used").count()
    new_count = Listing.query.filter_by(condition="new").count()

    return {
        "labels": ["Second-hand", "Nou"],
        "values": [used_count, new_count],
    }


def _get_users_by_role():
    buyers = User.query.filter_by(role=User.ROLE_BUYER).count()
    sellers = User.query.filter_by(role=User.ROLE_SELLER).count()
    admins = User.query.filter_by(role=User.ROLE_ADMIN).count()

    return {
        "labels": ["Buyer", "Seller", "Admin"],
        "values": [buyers, sellers, admins],
    }


def get_admin_analytics_data():
    from app.db_market import get_market_condition_distribution

    return {
        "evaluations_per_day": _get_evaluations_per_day(days=30),
        "evaluations_per_brand": _get_evaluations_per_brand(limit=10),
        "price_comparison_per_brand": _get_price_comparison_per_brand(limit=8),
        "condition_distribution_platform": _get_condition_distribution_platform(),
        "condition_distribution_market": get_market_condition_distribution(),
        "users_by_role": _get_users_by_role(),
    }