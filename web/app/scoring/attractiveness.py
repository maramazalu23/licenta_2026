from typing import Any, Dict, Optional


def _clean_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    value = str(value).strip()
    return value if value else None


def _to_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(value, high))


def compute_attractiveness_score(
    title: Optional[str] = None,
    description: Optional[str] = None,
    brand: Optional[str] = None,
    ram_gb: Optional[int] = None,
    condition: Optional[str] = None,
    price_asked: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Scor euristic 0-100 pentru calitatea / atractivitatea anuntului.
    Nu masoara pretul de piata in sine, ci calitatea informatiilor oferite.
    """

    title = _clean_str(title)
    description = _clean_str(description)
    brand = _clean_str(brand)
    condition = _clean_str(condition)
    ram_gb = _to_int(ram_gb)
    price_asked = _to_float(price_asked)

    score = 0
    details = {}

    # 1. Titlu
    if title:
        title_len = len(title)
        if title_len >= 35:
            score += 20
            details["title"] = {"points": 20, "status": "good"}
        elif title_len >= 15:
            score += 12
            details["title"] = {"points": 12, "status": "ok"}
        else:
            score += 5
            details["title"] = {"points": 5, "status": "weak"}
    else:
        details["title"] = {"points": 0, "status": "missing"}

    # 2. Descriere
    if description:
        desc_len = len(description)
        if desc_len >= 200:
            score += 25
            details["description"] = {"points": 25, "status": "good"}
        elif desc_len >= 80:
            score += 16
            details["description"] = {"points": 16, "status": "ok"}
        elif desc_len >= 20:
            score += 8
            details["description"] = {"points": 8, "status": "weak"}
        else:
            score += 3
            details["description"] = {"points": 3, "status": "very_short"}
    else:
        details["description"] = {"points": 0, "status": "missing"}

    # 3. Brand
    if brand:
        score += 10
        details["brand"] = {"points": 10, "status": "present"}
    else:
        details["brand"] = {"points": 0, "status": "missing"}

    # 4. RAM
    if ram_gb is not None:
        score += 10
        details["ram_gb"] = {"points": 10, "status": "present"}
    else:
        details["ram_gb"] = {"points": 0, "status": "missing"}

    # 5. Condition
    if condition:
        score += 10
        details["condition"] = {"points": 10, "status": "present"}
    else:
        details["condition"] = {"points": 0, "status": "missing"}

    # 6. Price asked
    if price_asked is not None and price_asked > 0:
        score += 10
        details["price_asked"] = {"points": 10, "status": "present"}
    else:
        details["price_asked"] = {"points": 0, "status": "missing"}

    # 7. Bonus daca titlul mentioneaza brandul
    if title and brand and brand.lower() in title.lower():
        score += 5
        details["title_brand_match"] = {"points": 5, "status": "yes"}
    else:
        details["title_brand_match"] = {"points": 0, "status": "no"}

    # 8. Bonus daca descrierea pare suficient de informativa
    keywords = 0
    if description:
        desc_lower = description.lower()
        for token in ["ssd", "hdd", "ram", "intel", "amd", "baterie", "display", "procesor", "inch", "video"]:
            if token in desc_lower:
                keywords += 1

    if keywords >= 3:
        score += 10
        details["description_keywords"] = {"points": 10, "status": "good", "count": keywords}
    elif keywords >= 1:
        score += 5
        details["description_keywords"] = {"points": 5, "status": "ok", "count": keywords}
    else:
        details["description_keywords"] = {"points": 0, "status": "weak", "count": keywords}

    final_score = int(round(_clamp(score, 0, 100)))

    if final_score >= 85:
        label = "excellent"
        explanation = "Anuntul este bine completat si ofera suficiente informatii pentru evaluare."
    elif final_score >= 70:
        label = "good"
        explanation = "Anuntul este destul de clar, dar mai poate fi imbunatatit."
    elif final_score >= 50:
        label = "average"
        explanation = "Anuntul contine doar o parte din informatiile utile."
    else:
        label = "weak"
        explanation = "Anuntul este prea sarac in detalii si ar trebui completat."

    recommendations = []
    if details["title"]["status"] in {"missing", "weak"}:
        recommendations.append("Adauga un titlu mai clar si mai descriptiv.")
    if details["description"]["status"] in {"missing", "very_short", "weak"}:
        recommendations.append("Completeaza descrierea cu specificatii si stare de utilizare.")
    if details["brand"]["status"] == "missing":
        recommendations.append("Specifică brandul produsului.")
    if details["ram_gb"]["status"] == "missing":
        recommendations.append("Specifică memoria RAM.")
    if details["condition"]["status"] == "missing":
        recommendations.append("Specifică starea produsului.")
    if details["price_asked"]["status"] == "missing":
        recommendations.append("Introdu pretul cerut.")
    if details["description_keywords"]["status"] == "weak":
        recommendations.append("Include mai multe detalii tehnice in descriere.")

    return {
        "score": final_score,
        "label": label,
        "explanation": explanation,
        "details": details,
        "recommendations": recommendations,
    }


if __name__ == "__main__":
    examples = [
        {
            "title": "Laptop Lenovo ThinkBook 16GB RAM SSD",
            "description": "Laptop in stare buna, procesor Intel, 16GB RAM, SSD 512GB, baterie buna, display fara defecte.",
            "brand": "Lenovo",
            "ram_gb": 16,
            "condition": "used",
            "price_asked": 2200,
        },
        {
            "title": "Laptop HP",
            "description": "merge bine",
            "brand": "HP",
            "ram_gb": None,
            "condition": "used",
            "price_asked": 1200,
        },
        {
            "title": None,
            "description": None,
            "brand": None,
            "ram_gb": None,
            "condition": None,
            "price_asked": None,
        },
    ]

    for ex in examples:
        print("=" * 80)
        print(compute_attractiveness_score(**ex))