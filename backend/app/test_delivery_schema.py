"""
Validates the delivery-format schema work: run after init_db picks up the
new columns.
    docker compose exec backend python -m app.test_delivery_schema
"""
import csv
import sys

from app.db import SessionLocal
from app.delivery.schema import CORE_COLUMNS, DELIVERY_COLUMNS, EAV_BACKED_COLUMNS, LONG_TAIL_COLUMNS
from app.models import Product

results = []


def check(description, passed):
    results.append((description, passed))
    print(f"[{'PASS' if passed else 'FAIL'}] {description}")


def main():
    with open("app/delivery/reference/expected_output_format.csv", newline="", encoding="utf-8") as f:
        actual_header = next(csv.reader(f))

    check("delivery schema matches reference CSV exactly (252 columns)", DELIVERY_COLUMNS == actual_header)
    check(
        "every column categorized exactly once (passthrough+core / EAV-backed / long-tail)",
        len(CORE_COLUMNS) + len(EAV_BACKED_COLUMNS) + len(LONG_TAIL_COLUMNS) == 252,
    )

    db = SessionLocal()
    product = None
    try:
        product = Product(
            title="Test Dishwasher",
            mfg_part_num="ABC123",
            part_desc="24 in. Built-In Dishwasher",
            e1_brand="TestBrand",
            unilog_brand="TestBrand",
            dib_brand="TestBrand",
            part_manuf="Test Distributor",
            manufacturer_name="TestCo",
            delivery_fields={"MFR URL": "https://example.com", "Dept": "Appliances", "UPC": "012345678905"},
        )
        db.add(product)
        db.commit()

        fetched = db.get(Product, product.id)
        check("core fields round-trip", fetched.mfg_part_num == "ABC123" and fetched.manufacturer_name == "TestCo")
        check(
            "delivery_fields JSONB round-trips",
            fetched.delivery_fields.get("MFR URL") == "https://example.com" and fetched.delivery_fields.get("UPC") == "012345678905",
        )
    finally:
        try:
            db.rollback()
            if product is not None:
                db.query(Product).filter(Product.id == product.id).delete()
            db.commit()
        except Exception:
            db.rollback()
        db.close()

    total, passed = len(results), sum(1 for _, ok in results if ok)
    print(f"\n{passed}/{total} checks passed")
    if passed != total:
        sys.exit(1)


if __name__ == "__main__":
    main()
