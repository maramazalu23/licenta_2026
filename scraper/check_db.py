import sqlite3

c = sqlite3.connect("data_out/products.db")

def s(q, p=()):
    return c.execute(q, p).fetchone()[0]

print("=== BASIC COUNTS ===")
print("products:", s("select count(1) from products"))
print("publi24:", s("select count(1) from products where source=?", ("publi24",)))
print("pcgarage:", s("select count(1) from products where source=?", ("pcgarage",)))

print("\n=== FIELD COVERAGE ===")
print("posted_at NOT NULL:", s("select count(1) from products where posted_at is not null and posted_at<>''"))
print("publi24 location NOT NULL:", s("select count(1) from products where source=? and location is not null and location<>''", ("publi24",)))
print("pcgarage model_guess NOT NULL:", s("select count(1) from products where source=? and model_guess is not null and model_guess<>''", ("pcgarage",)))
print("condition NOT NULL:", s("select count(1) from products where condition is not null and condition<>''"))

print("\n=== SNAPSHOTS ===")
print("snapshots:", s("select count(1) from price_snapshots"))
print("distinct urls:", s("select count(distinct url) from price_snapshots"))

print("\n=== SAMPLE MISSING ===")
print("publi24 missing location sample:")
print(c.execute("select url, title from products where source=? and (location is null or location='') limit 5", ("publi24",)).fetchall())

print("\nposted_at missing sample:")
print(c.execute("select source, url from products where posted_at is null or posted_at='' limit 5").fetchall())

print("\npcgarage missing model_guess sample:")
print(c.execute("select url, title from products where source=? and (model_guess is null or model_guess='') limit 5", ("pcgarage",)).fetchall())