from decimal import Decimal
from app.models import Product

def test_normalize_price_decimal():
    p = Product(
        source="publi24",
        category="laptopuri",
        url="x",
        title="t",
        price="6.398,99 lei",
    )
    assert p.price == Decimal("6398.99")