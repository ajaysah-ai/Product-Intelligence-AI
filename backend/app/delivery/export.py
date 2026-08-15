from app.delivery.schema import (
    ATTRIBUTE_SLOT_COUNT,
    DELIVERY_COLUMNS,
    FEATURE_SLOT_COUNT,
    LONG_TAIL_COLUMNS,
    attribute_label_col,
    attribute_uom_col,
    attribute_value_col,
    feature_col,
)

CORE_FIELD_TO_COLUMN = {
    "mfg_part_num": "Mfg_Part_Num",
    "part_desc": "Part_Desc",
    "e1_brand": "E1_Brand",
    "unilog_brand": "Unilog_Brand",
    "dib_brand": "DIB_Brand",
    "part_manuf": "Part_Manuf",
    "manufacturer_name": "MANUFACTURER_NAME",
    "title": "Product Name",
}


def build_delivery_row(core: dict, delivery_fields: dict | None, attribute_rows: list[dict]) -> dict:
    """core: {"mfg_part_num","part_desc","e1_brand","unilog_brand","dib_brand",
    "part_manuf","manufacturer_name","title"}.
    delivery_fields: {exact column name: value} for the long-tail columns.
    attribute_rows: [{"attribute_type": "spec"|"feature", "attribute_key",
    "attribute_value", "unit"}], in the order they should fill numbered slots.

    Returns a dict with every key in DELIVERY_COLUMNS present (empty string
    for anything unknown) — safe to pass straight to csv.DictWriter.
    """
    row = {col: "" for col in DELIVERY_COLUMNS}

    for field, column in CORE_FIELD_TO_COLUMN.items():
        value = core.get(field)
        if value is not None:
            row[column] = str(value)

    delivery_fields = delivery_fields or {}
    for column in LONG_TAIL_COLUMNS:
        value = delivery_fields.get(column)
        if value is not None and value != "":
            row[column] = str(value)

    spec_rows = [a for a in attribute_rows if a.get("attribute_type") == "spec"][:ATTRIBUTE_SLOT_COUNT]
    for i, attr in enumerate(spec_rows, start=1):
        row[attribute_label_col(i)] = str(attr.get("attribute_key") or "")
        row[attribute_value_col(i)] = str(attr.get("attribute_value") or "")
        row[attribute_uom_col(i)] = str(attr.get("unit") or "")

    feature_rows = [a for a in attribute_rows if a.get("attribute_type") == "feature"][:FEATURE_SLOT_COUNT]
    for i, attr in enumerate(feature_rows, start=1):
        row[feature_col(i)] = str(attr.get("attribute_value") or "")

    return row
