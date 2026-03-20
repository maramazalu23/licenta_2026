from typing import Any, Dict, Optional

from app.scoring.price_engine import estimate_price
from app.scoring.depreciation import compute_depreciation_score
from app.scoring.attractiveness import compute_attractiveness_score


def _clean_condition(value: Optional[str]) -> str:
    value = str(value).strip().lower() if value is not None else ""
    return value if value in {"used", "new"} else "used"


def evaluate_listing(
    title: Optional[str] = None,
    description: Optional[str] = None,
    brand: Optional[str] = None,
    ram_gb: Optional[int] = None,
    model_family: Optional[str] = None,
    condition: Optional[str] = None,
    price_asked: Optional[float] = None,
) -> Dict[str, Any]:
    condition = _clean_condition(condition)

    price_result = estimate_price(
        brand=brand,
        ram_gb=ram_gb,
        model_family=model_family,
        condition=condition,
        price_asked=price_asked,
    )

    market_reference = price_result.get("market_reference", {})
    outputs = price_result.get("outputs", {})

    if condition == "used":
        depreciation_result = compute_depreciation_score(
            fair_price_used=outputs.get("fair_price_used"),
            new_median=market_reference.get("new_median"),
        )
    else:
        depreciation_result = {
            "score": None,
            "retention_ratio": None,
            "depreciation_pct": None,
            "label": "not_applicable",
            "explanation": "Scorul de depreciere se calculeaza doar pentru produse second-hand.",
        }

    attractiveness_result = compute_attractiveness_score(
        title=title,
        description=description,
        brand=brand,
        ram_gb=ram_gb,
        condition=condition,
        price_asked=price_asked,
    )

    return {
        "input": {
            "title": title,
            "description": description,
            "brand": brand,
            "ram_gb": ram_gb,
            "model_family": model_family,
            "condition": condition,
            "price_asked": price_asked,
        },
        "price_estimation": price_result,
        "depreciation": depreciation_result,
        "attractiveness": attractiveness_result,
    }


if __name__ == "__main__":
    sample = evaluate_listing(
        title="Laptop Lenovo ThinkBook 16GB RAM SSD",
        description="Laptop in stare buna, procesor Intel, 16GB RAM, SSD 512GB, baterie buna, display fara defecte.",
        brand="Lenovo",
        ram_gb=16,
        model_family="ThinkBook",
        condition="used",
        price_asked=2200,
    )

    from pprint import pprint
    pprint(sample)