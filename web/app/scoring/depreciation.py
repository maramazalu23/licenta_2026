from typing import Any, Dict, Optional


def _to_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(value, high))


def compute_depreciation_score(
    fair_price_used: Optional[float],
    new_median: Optional[float],
) -> Dict[str, Any]:
    """
    Calculeaza deprecierea fata de pretul median pentru produse noi
    si intoarce un scor 0-100.

    Interpretare:
    - scor mare = depreciere sanatoasa / plauzibila pentru second-hand
    - scor mic = fie depreciere prea mica, fie date insuficiente
    """

    fair_price_used = _to_float(fair_price_used)
    new_median = _to_float(new_median)

    if fair_price_used is None or new_median is None or new_median <= 0:
        return {
            "score": None,
            "retention_ratio": None,
            "depreciation_pct": None,
            "label": "unknown",
            "explanation": "Nu exista suficiente date pentru estimarea deprecierii.",
        }

    retention_ratio = fair_price_used / new_median
    depreciation_pct = (1 - retention_ratio) * 100

    # Heuristica MVP:
    # - 40%-75% depreciere: zona buna pentru SH
    # - prea mica: suspect de scump fata de nou
    # - prea mare: posibil produs foarte vechi / segment slab / date zgomotoase
    if 40 <= depreciation_pct <= 75:
        score = 90
        label = "healthy"
        explanation = "Deprecierea estimata se afla intr-un interval plauzibil pentru piata second-hand."
    elif 25 <= depreciation_pct < 40:
        score = 65
        label = "low_depreciation"
        explanation = "Deprecierea estimata este relativ mica, ceea ce poate indica un pret SH ridicat fata de segmentul nou."
    elif 75 < depreciation_pct <= 90:
        score = 70
        label = "high_depreciation"
        explanation = "Deprecierea estimata este ridicata, dar inca plauzibila pentru produse mai vechi sau mai slab pozitionate."
    elif depreciation_pct < 25:
        score = 30
        label = "very_low_depreciation"
        explanation = "Deprecierea estimata este foarte mica, ceea ce sugereaza un pret second-hand apropiat de cel al produselor noi."
    else:
        score = 45
        label = "extreme_depreciation"
        explanation = "Deprecierea estimata este foarte mare si poate reflecta fie uzura accentuata, fie comparabile imperfecte."

    return {
        "score": int(_clamp(score, 0, 100)),
        "retention_ratio": round(retention_ratio, 2),
        "depreciation_pct": round(depreciation_pct, 2),
        "label": label,
        "explanation": explanation,
    }


if __name__ == "__main__":
    examples = [
        {"fair_price_used": 800, "new_median": 3048.99},
        {"fair_price_used": 499, "new_median": 2316.32},
        {"fair_price_used": 800, "new_median": 1100},
        {"fair_price_used": None, "new_median": 3000},
    ]

    for ex in examples:
        print("=" * 80)
        print(compute_depreciation_score(**ex))