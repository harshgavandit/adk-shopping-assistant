"""Fixed demo catalog. Prices are illustrative, not live retailer prices."""
PRODUCTS = {
    "Pixel 9": ("Smartphones", 70000),
    "iPhone 16": ("Smartphones", 90000),
    "Galaxy S25": ("Smartphones", 75000),
    "MacBook Air M3": ("Laptops", 110000),
    "Dell Inspiron": ("Laptops", 65000),
    "Sony WH-1000XM6": ("Headphones", 30000),
    "Boat Rockerz": ("Headphones", 2000),
}


def catalog_text():
    return "\n".join(f"- {name}: {category}, INR {price:,}" for name, (category, price) in PRODUCTS.items())
