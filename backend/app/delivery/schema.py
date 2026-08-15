"""
Canonical column list for the hackathon's expected delivery CSV format.
Extracted verbatim from app/delivery/reference/expected_output_format.csv —
if the hackathon organizers revise the format, replace that file and rerun
the categorization at the bottom of this module to check for drift.
"""

DELIVERY_COLUMNS = [
    "MFR URL", "Ref URL 1", "Ref URL 2", "Ref URL 3", "Ref URL 4", "Ref URL 5",
    "PART_NUMBER", "Dept", "Class", "Fine", "SKU - MY_PART_NUMBER",
    "Mfg_Part_Num", "Part_Desc", "E1_Brand", "Unilog_Brand", "DIB_Brand", "Part_Manuf",
    "MANUFACTURER_NAME", "BRAND_NAME", "TRADE_NAME",
    "MANUFACTURER_PART_NUMBER", "ALTERNATE_PART_NUMBER", "Classpath",
    "MOBILE_DESC", "INVOICE_DESC", "SHORT_DESC", "LONG_DESC1", "RETAIL_DESC", "MARKETING_DESCRIPTION",
]

# ITEM_FEATURES_1..20 — sourced from product_attributes EAV rows (attribute_type='feature')
FEATURE_SLOT_COUNT = 20
DELIVERY_COLUMNS += [f"ITEM_FEATURES_{i}" for i in range(1, FEATURE_SLOT_COUNT + 1)]

DELIVERY_COLUMNS += [
    "With", "Standard/Approvals", "Prop 65", "Application", "Includes", "Product Name",
]

# ATTRIBUTE_LABEL/VALUE/UOM 1..50 — sourced from product_attributes EAV rows (attribute_type='spec')
ATTRIBUTE_SLOT_COUNT = 50
for _i in range(1, ATTRIBUTE_SLOT_COUNT + 1):
    DELIVERY_COLUMNS += [f"ATTRIBUTE_LABEL {_i}", f"ATTRIBUTE_VALUE {_i}", f"ATTRIBUTE_UOM {_i}"]

DELIVERY_COLUMNS += [
    "UPC", "EAN", "GTIN", "UNSPSC", "Warranty",
    "List Price", "Selling Qty", "Selling UOM", "Standard Packaging Information",
    "LENGTH", "LENGTH_UOM", "HEIGHT", "HEIGHT_UOM", "WIDTH", "WIDTH_UOM",
    "WEIGHT", "WEIGHT_UOM", "VOLUME", "VOLUME_UOM",
    "Product Image", "Alternate Image 1", "Alternate Image 2", "Alternate Image 3", "Alternate Image 4",
    "SDS", "SDS_1", "Warranty Information", "Catalog", "Specification Sheet",
    "Instruction/Installation Manual", "Service Manual", "Owners/User Manual", "Line Drawing",
    "MTR", "RoHS", "Full Engineering Drawing", "Energy Star Guide", "Technical Bulletin",
    "Submittal", "Compatibility Chart", "Size Chart", "Product Label/Insert",
    "Video Link", "Video Link 1", "Country Of Origin", "Discontinued", "Actual Image (Yes/No)",
]

assert len(DELIVERY_COLUMNS) == 252, f"Expected 252 columns, built {len(DELIVERY_COLUMNS)} — check for drift"

# The 6 input columns, copied verbatim into the output (same names in both files)
PASSTHROUGH_COLUMNS = ["Mfg_Part_Num", "Part_Desc", "E1_Brand", "Unilog_Brand", "DIB_Brand", "Part_Manuf"]

# Columns backed by the product_attributes EAV table, not by Product.delivery_fields directly
ATTRIBUTE_LABEL_COLUMNS = [f"ATTRIBUTE_LABEL {i}" for i in range(1, ATTRIBUTE_SLOT_COUNT + 1)]
ATTRIBUTE_VALUE_COLUMNS = [f"ATTRIBUTE_VALUE {i}" for i in range(1, ATTRIBUTE_SLOT_COUNT + 1)]
ATTRIBUTE_UOM_COLUMNS = [f"ATTRIBUTE_UOM {i}" for i in range(1, ATTRIBUTE_SLOT_COUNT + 1)]
FEATURE_COLUMNS = [f"ITEM_FEATURES_{i}" for i in range(1, FEATURE_SLOT_COUNT + 1)]
EAV_BACKED_COLUMNS = set(ATTRIBUTE_LABEL_COLUMNS + ATTRIBUTE_VALUE_COLUMNS + ATTRIBUTE_UOM_COLUMNS + FEATURE_COLUMNS)

# "Core" columns get real Product/TempDetectedProduct table columns (see models.py);
# everything else in DELIVERY_COLUMNS that isn't EAV-backed lives in the
# delivery_fields JSONB column, keyed by the exact column name above.
CORE_COLUMNS = set(PASSTHROUGH_COLUMNS) | {"MANUFACTURER_NAME"}

LONG_TAIL_COLUMNS = [c for c in DELIVERY_COLUMNS if c not in EAV_BACKED_COLUMNS and c not in CORE_COLUMNS]


def attribute_label_col(slot: int) -> str:
    return f"ATTRIBUTE_LABEL {slot}"


def attribute_value_col(slot: int) -> str:
    return f"ATTRIBUTE_VALUE {slot}"


def attribute_uom_col(slot: int) -> str:
    return f"ATTRIBUTE_UOM {slot}"


def feature_col(slot: int) -> str:
    return f"ITEM_FEATURES_{slot}"
