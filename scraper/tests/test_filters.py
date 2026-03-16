from app.filters import is_valid_publi24_laptop


def test_filter_accepts_laptop_like():
    assert is_valid_publi24_laptop(
        "Laptop Lenovo ThinkPad T480",
        "i5 16GB 512SSD",
        "https://x"
    ) is True


def test_filter_rejects_battery():
    assert is_valid_publi24_laptop(
        "Baterie Lenovo T480",
        "baterie noua",
        "https://x"
    ) is False


def test_filter_rejects_phone():
    assert is_valid_publi24_laptop(
        "iPhone 11 Pro",
        "telefon foarte bun",
        "https://x"
    ) is False


def test_filter_rejects_tablet():
    assert is_valid_publi24_laptop(
        "Schimb laptop cu tableta Samsung",
        "tableta impecabila",
        "https://x"
    ) is False


def test_filter_rejects_wireless_module():
    assert is_valid_publi24_laptop(
        "Modul wireless pentru laptop",
        "wifi wlan",
        "https://x"
    ) is False


def test_filter_accepts_legit_laptop_even_if_mentions_keyboard():
    assert is_valid_publi24_laptop(
        "Laptop ASUS TUF F15 cu tastatura iluminata",
        "15.6 inch i5 16GB 512GB SSD",
        "https://x"
    ) is True


def test_filter_accepts_legit_laptop_even_if_mentions_dvd():
    assert is_valid_publi24_laptop(
        "Laptop Dell Latitude E6540 DVD",
        "15.6 inch i7 8GB 256GB SSD",
        "https://x"
    ) is True


def test_filter_rejects_docking_station():
    assert is_valid_publi24_laptop(
        "2 Docking Station / statie laptop HP A7E32AA 90W",
        "statie pentru laptop hp",
        "https://x"
    ) is False


def test_filter_rejects_chromebox():
    assert is_valid_publi24_laptop(
        "HP Chromebox G2 Office Mini PC",
        "mini pc office",
        "https://x"
    ) is False


def test_filter_rejects_surface_pro():
    assert is_valid_publi24_laptop(
        "Microsoft Surface Pro 9, i7, 16 GB RAM, 512 GB SSD",
        "tableta premium cu tastatura",
        "https://x"
    ) is False


def test_filter_rejects_mac_studio():
    assert is_valid_publi24_laptop(
        "Vand Mac Studio M1 Max",
        "desktop apple",
        "https://x"
    ) is False


def test_filter_rejects_bundle_with_auto_tester():
    assert is_valid_publi24_laptop(
        "Pachet Laptop + interfata diagnoza auto multimarca",
        "kit tester auto",
        "https://x"
    ) is False


def test_filter_rejects_dezmembrez():
    assert is_valid_publi24_laptop(
        "Dezmembrez Laptop DELL Inspiron 5558",
        "pentru piese",
        "https://x"
    ) is False