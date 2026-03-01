from app.filters import is_valid_publi24_laptop

def test_filter_accepts_laptop_like():
    assert is_valid_publi24_laptop("Laptop Lenovo ThinkPad T480", "i5 16GB 512SSD", "https://x") is True

def test_filter_rejects_accessory_like():
    assert is_valid_publi24_laptop("Baterie Lenovo T480", "baterie noua", "https://x") is False