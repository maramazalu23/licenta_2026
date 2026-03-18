from typing import Any, Dict, Optional

from app.db_market import get_price_stats


def _to_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(value, high))


def _round_price(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return round(float(value), 2)


def _segment_confidence(source_level: str, used_n: int) -> str:
    if source_level == "brand+ram+family" and used_n >= 5:
        return "high"
    if source_level in {"brand+ram+family", "brand+ram", "brand+family"} and used_n >= 3:
        return "medium"
    if source_level in {"brand", "ram"} and used_n >= 3:
        return "low"
    return "very_low"


def _compute_fair_price_used(q1: Optional[float], median: Optional[float], q3: Optional[float]) -> Optional[float]:
    if median is None:
        return None

    if q1 is not None and q3 is not None:
        # MVP defensabil: pretul recomandat pentru SH este mediana segmentului.
        # Q1 si Q3 raman interval de referinta.
        return _round_price(median)

    return _round_price(median)


def _compute_deal_rating(price_asked: Optional[float], q1: Optional[float], q3: Optional[float], fair_price_used: Optional[float]) -> Dict[str, Any]:
    if price_asked is None:
        return {
            "label": "unknown",
            "score": None,
            "delta_vs_fair": None,
            "explanation": "Pretul cerut nu a fost furnizat.",
        }

    if fair_price_used is None:
        return {
            "label": "unknown",
            "score": None,
            "delta_vs_fair": None,
            "explanation": "Segmentul nu are suficiente comparabile pentru a evalua pretul.",
        }

    delta = _round_price(price_asked - fair_price_used)

    if q1 is not None and q3 is not None:
        if price_asked < q1:
            return {
                "label": "very_good",
                "score": 90,
                "delta_vs_fair": delta,
                "explanation": "Pretul este sub primul quartil al segmentului si pare foarte avantajos.",
            }
        if q1 <= price_asked <= q3:
            # Mai aproape de mediana = scor mai bun
            spread = max(q3 - q1, 1.0)
            proximity = abs(price_asked - fair_price_used) / spread
            score = int(round(85 - 25 * proximity))
            score = int(_clamp(score, 70, 85))
            return {
                "label": "fair",
                "score": score,
                "delta_vs_fair": delta,
                "explanation": "Pretul este in intervalul tipic al segmentului.",
            }

        upper_gap = price_asked - q3
        spread = max(q3 - q1, 1.0)
        relative_gap = upper_gap / spread

        if relative_gap <= 0.35:
            return {
                "label": "slightly_high",
                "score": 55,
                "delta_vs_fair": delta,
                "explanation": "Pretul este usor peste intervalul tipic al segmentului.",
            }

        return {
            "label": "overpriced",
            "score": 25,
            "delta_vs_fair": delta,
            "explanation": "Pretul este mult peste intervalul tipic al segmentului.",
        }

    # fallback daca exista doar median
    rel = abs(price_asked - fair_price_used) / max(fair_price_used, 1.0)
    if rel <= 0.10:
        return {
            "label": "fair",
            "score": 75,
            "delta_vs_fair": delta,
            "explanation": "Pretul este apropiat de valoarea tipica estimata pentru segment.",
        }
    if price_asked < fair_price_used:
        return {
            "label": "good",
            "score": 85,
            "delta_vs_fair": delta,
            "explanation": "Pretul este sub valoarea tipica estimata pentru segment.",
        }

    return {
        "label": "high",
        "score": 45,
        "delta_vs_fair": delta,
        "explanation": "Pretul este peste valoarea tipica estimata pentru segment.",
    }


def estimate_price(
    brand: Optional[str],
    ram_gb: Optional[int],
    model_family: Optional[str],
    price_asked: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Motorul principal pentru estimarea pretului.
    Consuma exclusiv get_price_stats() din db_market.py.
    """

    stats = get_price_stats(
        brand=brand,
        ram_gb=ram_gb,
        model_family=model_family,
    )

    used = stats.get("used", {})
    new = stats.get("new", {})

    used_n = int(used.get("n", 0) or 0)
    q1 = _to_float(used.get("q1"))
    median = _to_float(used.get("median"))
    q3 = _to_float(used.get("q3"))
    new_median = _to_float(new.get("median"))
    price_asked = _to_float(price_asked)

    fair_price_used = _compute_fair_price_used(q1, median, q3)

    if fair_price_used is not None and new_median not in (None, 0):
        retention_ratio = _round_price(fair_price_used / new_median)
    else:
        retention_ratio = None

    if retention_ratio is not None:
        depreciation_pct = _round_price((1 - retention_ratio) * 100)
    else:
        depreciation_pct = None

    deal = _compute_deal_rating(
        price_asked=price_asked,
        q1=q1,
        q3=q3,
        fair_price_used=fair_price_used,
    )

    source_level = stats.get("source_level", "no_match")
    confidence = _segment_confidence(source_level, used_n)

    return {
        "inputs": {
            "brand": brand,
            "ram_gb": ram_gb,
            "model_family": model_family,
            "price_asked": price_asked,
        },
        "segment": {
            "source_level": source_level,
            "confidence": confidence,
            "filters_used": stats.get("filters_used", {}),
            "used_n": used_n,
            "new_n": int(new.get("n", 0) or 0),
        },
        "market_reference": {
            "used_q1": q1,
            "used_median": median,
            "used_q3": q3,
            "new_median": new_median,
        },
        "outputs": {
            "fair_price_used": fair_price_used,
            "retention_ratio_vs_new": retention_ratio,
            "depreciation_pct_vs_new": depreciation_pct,
            "deal_rating_label": deal["label"],
            "deal_rating_score": deal["score"],
            "delta_vs_fair_price": deal["delta_vs_fair"],
        },
        "explanations": {
            "pricing": (
                "Pretul recomandat pentru produsul second-hand este aproximat prin mediana segmentului "
                "de comparabile gasite in baza de date."
                if fair_price_used is not None
                else "Nu exista suficiente comparabile pentru a estima robust pretul recomandat."
            ),
            "deal": deal["explanation"],
        },
    }


if __name__ == "__main__":
    examples = [
        {"brand": "Lenovo", "ram_gb": 16, "model_family": "IdeaPad", "price_asked": 2200},
        {"brand": "Lenovo", "ram_gb": 16, "model_family": "ThinkBook", "price_asked": 2200},
        {"brand": "Dell", "ram_gb": 8, "model_family": "Latitude", "price_asked": 900},
        {"brand": "HP", "ram_gb": 8, "model_family": "EliteBook", "price_asked": 1200},
    ]

    for ex in examples:
        print("=" * 80)
        print(estimate_price(**ex))