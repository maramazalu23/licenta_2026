from app.core.utils import guess_brand

def test_guess_brand():
    assert guess_brand("Laptop ASUS ROG Strix") == "ASUS"
    assert guess_brand("lenovo thinkpad t14") == "LENOVO"