"""
eHive Record Updater  v8.02.12
================================
Automates batch updating of existing eHive object records from a CSV file.
Built for the Archaeology, Archive, Natural Science, and Photography catalogue
types at the University of Bristol (DAAC).

Requirements:
    pip install playwright pandas
    playwright install chromium

Usage:
    1. Run: python ehive_automation.py
    2. Answer the prompts for CSV path and append/replace mode
    3. Log in manually in the browser window that opens
    4. Press Enter in the terminal to start the automation

Modes:
    UPDATE  — updates existing records. CSV must have a "url" column.
              Supports Append or Replace for existing field values.
    CREATE  — creates new records from a template via "Create Similar Record".
              CSV does NOT need a "url" column (template is set at startup).
              Always runs in Replace mode (overwrites template values).

CSV columns — Detail Fields tab (leave any cell blank to skip):
    url, object_number, accession_date, name_title,
    collection_type, classification, specimen_category,
    specimen_category_notes, object_type, brief_description,
    public_description, date_made, period, production_notes,
    field_collection_place, field_collection_date,
    field_collection_notes, site_name, stratigraphy_description,
    current_location, location_notes, medium_materials,
    physical_characteristics, inscription_marks,
    measurements, subject_keywords, general_notes,
    item_count, item_count_notes,
    part_ids, part_descriptions,
    other_maker, other_maker_role,
    other_number, other_number_type

CSV columns — Natural Science only (Detail Fields tab):
    habitat_keyword, habitat_description

CSV columns — Acquisition tab:
    related_acquisition_record,
    named_collection, credit_line, acquisition_notes,
    provenance_date, provenance_details, provenance_person,
    provenance_place,
    acquisition_valuation, acquisition_price_local,
    acquisition_price_foreign,
    funder, funding_amount, funding_type

CSV columns — Administration tab:
    record_status, legal_ownership_status, restriction_type,
    rights_expiry_date, rights_notes, rights_owner,
    rights_start_date, rights_type,
    comments, comments_date, comments_person,
    general_flag, general_notes_admin

    subject_keywords  — semicolon-separated e.g. "Vessel; Sherd; Rim Sherd"
    part_ids          — semicolon-separated e.g. "2024.1.1a; 2024.1.1b"
    part_descriptions — semicolon-separated, one description per part ID
                        e.g. "Lid; Base"
                        If fewer descriptions than IDs are given, remaining
                        parts get a blank description.
"""

import argparse
import os
import pandas as pd
import asyncio
import traceback
from playwright.async_api import async_playwright

# ─────────────────────────────────────────────
# CONFIGURATION — edit these before running
# ─────────────────────────────────────────────
ACCOUNT_ID  = "203598"
CSV_PATH    = r"C:\Users\ab1426\OneDrive - University of Bristol\Desktop\ehive\objects_test.csv"

HEADLESS    = False
FIELD_DELAY = 0.5

# Put this value in any CSV cell to explicitly blank that field
CLEAR = "CLEAR"
# ─────────────────────────────────────────────

# ─────────────────────────────────────────────
# STABLE FIELD SELECTORS (dlf_ IDs never change)
# Fields are keyed by catalogue type where IDs differ.
# ─────────────────────────────────────────────

# Archaeology fields (dlf_302050... prefix, sections _66–_76)
FIELDS = {
    # Basic Object Details
    "object_number":            {"type": "text",     "id": "dlf_302050100_66"},
    "accession_date":           {"type": "text",     "id": "dlf_302050101_66"},
    "name_title":               {"type": "text",     "id": "dlf_302050102_66"},
    "collection_type":          {"type": "combobox", "id": "dlf_302050103_66"},
    "classification":           {"type": "combobox", "id": "dlf_302050104_66"},
    "specimen_category":        {"type": "combobox", "id": "dlf_302050105_66"},
    "specimen_category_notes":  {"type": "text",     "id": "dlf_302050161_66"},
    "object_type":              {"type": "combobox", "id": "dlf_302050106_66"},
    "brief_description":        {"type": "text",     "id": "dlf_302050108_66"},
    "public_description":       {"type": "text",     "id": "dlf_302050109_66"},
    # Production
    "date_made":                {"type": "text",     "id": "dlf_302050112_67"},
    "period":                   {"type": "combobox", "id": "dlf_500200255_67"},
    "production_notes":         {"type": "text",     "id": "dlf_500200606_67"},
    # Field Collection
    "field_collection_place":   {"type": "text",     "id": "dlf_302050120_68"},
    "field_collection_date":    {"type": "text",     "id": "dlf_302050122_68"},
    "field_collection_notes":   {"type": "text",     "id": "dlf_500200249_68"},
    "site_name":                {"type": "text",     "id": "dlf_302050124_68"},
    "stratigraphy_description": {"type": "text",     "id": "dlf_302050125_68"},
    # Location
    "current_location":         {"type": "combobox", "id": "dlf_302050126_69"},
    "location_notes":           {"type": "text",     "id": "dlf_302050127_69"},
    # Physical Details
    "medium_materials":         {"type": "text",     "id": "dlf_302050133_71"},
    "physical_characteristics": {"type": "text",     "id": "dlf_302050134_71"},
    "inscription_marks":        {"type": "text",     "id": "dlf_302050137_71"},
    # Measurements
    "measurements":             {"type": "text",     "id": "dlf_302050139_72"},
    # General Notes
    "general_notes":            {"type": "text",     "id": "dlf_302050157_76"},
}

# Archive fields (dlf_302040... prefix, sections _54–_64)
ARCHIVE_FIELDS = {
    # Basic Object Details
    "object_number":            {"type": "text",     "id": "dlf_302040100_54"},
    "accession_date":           {"type": "text",     "id": "dlf_302040101_54"},
    "name_title":               {"type": "text",     "id": "dlf_302040102_54"},
    "object_type":              {"type": "combobox", "id": "dlf_302040108_54"},
    "brief_description":        {"type": "text",     "id": "dlf_302040110_54"},
    "public_description":       {"type": "text",     "id": "dlf_302040111_54"},
    # Production
    "date_made":                {"type": "text",     "id": "dlf_302040114_55"},
    "period":                   {"type": "combobox", "id": "dlf_500201316_55"},
    "production_notes":         {"type": "text",     "id": "dlf_500200604_55"},
    # Location
    "current_location":         {"type": "combobox", "id": "dlf_302040118_56"},
    "location_notes":           {"type": "text",     "id": "dlf_302040119_56"},
    # item_count / item_count_notes are handled by fill_item_count() — not listed here
    # Physical Details
    "medium_and_materials":     {"type": "text",     "id": "dlf_302040125_58"},
    "physical_characteristics": {"type": "text",     "id": "dlf_302040126_58"},
    "inscription_marks":        {"type": "text",     "id": "dlf_302040127_58"},
    # Measurements
    "measurements":             {"type": "text",     "id": "dlf_302040130_59"},
    # Context
    "significance":             {"type": "text",     "id": "dlf_302040135_60"},
    # General Notes
    "general_notes":            {"type": "text",     "id": "dlf_302040148_63"},
    "catalogued_date":          {"type": "text",     "id": "dlf_302040150_64"},
    "cataloguer":               {"type": "combobox", "id": "dlf_302040149_64"},
}

# Photography and Multimedia fields (dlf_302030... prefix, sections _29–_40)
# Verified against HTML snapshot. No Field Collection section in Photography.
PHOTOGRAPHY_FIELDS = {
    # Basic Object Details
    "object_number":            {"type": "text",     "id": "dlf_302030100_29"},
    "accession_date":           {"type": "text",     "id": "dlf_302030101_29"},
    "name_title":               {"type": "text",     "id": "dlf_302030102_29"},
    "collection_type":          {"type": "combobox", "id": "dlf_302030105_29"},
    "classification":           {"type": "combobox", "id": "dlf_302030106_29"},
    "object_type":              {"type": "combobox", "id": "dlf_302030107_29"},
    "brief_description":        {"type": "text",     "id": "dlf_302030109_29"},
    "public_description":       {"type": "text",     "id": "dlf_302030110_29"},
    # Production
    "date_made":                {"type": "text",     "id": "dlf_302030113_30"},
    "period":                   {"type": "combobox", "id": "dlf_500200281_30"},
    "production_notes":         {"type": "text",     "id": "dlf_500200605_30"},
    # Location
    "current_location":         {"type": "combobox", "id": "dlf_302030117_31"},
    "location_notes":           {"type": "text",     "id": "dlf_302030118_31"},
    # Physical Details
    "medium_materials":         {"type": "text",     "id": "dlf_302030124_33"},
    "physical_characteristics": {"type": "text",     "id": "dlf_302030125_33"},
    "inscription_marks":        {"type": "text",     "id": "dlf_302030128_33"},
    # Measurements
    "measurements":             {"type": "text",     "id": "dlf_302030131_34"},
    # General Notes
    "general_notes":            {"type": "text",     "id": "dlf_302030152_39"},
}

# Natural Science — full field set with its own dlf_ IDs
NS_FIELDS = {
    # Basic Object Details
    "object_number":                      {"type": "text",     "id": "dlf_302070100_1"},
    "accession_date":                     {"type": "text",     "id": "dlf_302070101_1"},
    "name_title":                         {"type": "text",     "id": "dlf_302070103_1"},
    "object_type":                        {"type": "combobox", "id": "dlf_302070104_1"},
    # Identification
    "identified_by":                      {"type": "combobox", "id": "dlf_302070109_2"},
    "identification_date":                {"type": "text",     "id": "dlf_302070110_2"},
    "taxonomic_classification":           {"type": "combobox", "id": "dlf_302070106_2"},
    "taxonomic_classification_notes":     {"type": "text",     "id": "dlf_302070111_2"},
    "taxonomic_qualifier":                {"type": "combobox", "id": "dlf_302070107_2"},
    "taxonomic_type_indicator":           {"type": "combobox", "id": "dlf_302070108_2"},
    "type_id_reliability_level":          {"type": "combobox", "id": "dlf_500200261_2"},
    # Specimen
    "specimen_category":                  {"type": "combobox", "id": "dlf_302070112_3"},
    "specimen_category_notes":            {"type": "text",     "id": "dlf_302070113_3"},
    "specimen_details":                   {"type": "text",     "id": "dlf_500201391_3"},
    "period":                             {"type": "combobox", "id": "dlf_500201320_3"},
    "brief_description":                  {"type": "text",     "id": "dlf_302070116_3"},
    "public_description":                 {"type": "text",     "id": "dlf_302070117_3"},
    # Field Collection
    "field_collector":                    {"type": "combobox", "id": "dlf_302070120_4"},
    "field_collector_role":               {"type": "combobox", "id": "dlf_302070157_4"},
    "field_collection_place":             {"type": "text",     "id": "dlf_302070121_4"},
    "field_collection_date":              {"type": "text",     "id": "dlf_302070123_4"},
    "field_collection_time":              {"type": "text",     "id": "dlf_302070124_4"},
    "field_collection_notes":             {"type": "text",     "id": "dlf_302070158_4"},
    "site_name":                          {"type": "text",     "id": "dlf_302070127_5"},
    # Location
    "current_location":                   {"type": "combobox", "id": "dlf_302070128_6"},
    "location_notes":                     {"type": "text",     "id": "dlf_302070129_6"},
    # Habitat & Geology
    "habitat_keyword":                    {"type": "combobox", "id": "dlf_500201378_8"},
    "habitat_description":                {"type": "text",     "id": "dlf_500200262_8"},
    "geological_formation":               {"type": "combobox", "id": "dlf_500200263_8"},
    "geological_age":                     {"type": "combobox", "id": "dlf_500201363_8"},
    "geological_age_description":         {"type": "text",     "id": "dlf_500200264_8"},
    "stratigraphy_description":           {"type": "text",     "id": "dlf_302070136_8"},
    "stratigraphy_keyword":               {"type": "combobox", "id": "dlf_500201399_8"},
    # Measurements
    "measurements":                       {"type": "text",     "id": "dlf_302070138_10"},
    # Context
    "significance":                       {"type": "text",     "id": "dlf_302070143_11"},
    "subject_association_description":    {"type": "text",     "id": "dlf_302070144_11"},
    # General
    "general_notes":                      {"type": "text",     "id": "dlf_302070153_14"},
    "catalogued_date":                    {"type": "text",     "id": "dlf_302070155_15"},
    "cataloguer":                         {"type": "combobox", "id": "dlf_302070154_15"},
}

def get_fields(cat_type):
    """Return the correct field map for the given catalogue type."""
    if cat_type == "naturalscience":
        return NS_FIELDS
    elif cat_type == "archive":
        return ARCHIVE_FIELDS
    elif cat_type == "photography":
        return PHOTOGRAPHY_FIELDS
    return FIELDS  # archaeology (default)

# ─────────────────────────────────────────────
# ACQUISITION TAB FIELDS (dlf_302080... prefix)
# These are the same across all catalogue types.
# Tab must be clicked before these fields are accessible.
# ─────────────────────────────────────────────
ACQUISITION_FIELDS = {
    # Credit Line panel
    "named_collection":         {"type": "combobox", "id": "dlf_302080207_117"},
    "credit_line":              {"type": "text",     "id": "dlf_302080208_117"},
    # General Notes panel
    "acquisition_notes":        {"type": "text",     "id": "dlf_302080211_119"},
    # Value panel
    "acquisition_valuation":    {"type": "text",     "id": "dlf_302080201_116"},
    "acquisition_price_local":  {"type": "text",     "id": "dlf_302080203_116"},
    "acquisition_price_foreign":{"type": "text",     "id": "dlf_302080202_116"},
}

# Provenance repeating set (Acquisition tab, _120 panel)
PROVENANCE_FIELDS = {
    "fieldset_legend": "Provenance",
    "add_button":      "Add Another Set",
    "delete_button":   "Delete Set",
    "fields": {
        "provenance_date":    {"type": "text",     "id": "dlf_302080213_120"},
        "provenance_details": {"type": "text",     "id": "dlf_302080212_120"},
        "provenance_person":  {"type": "combobox", "id": "dlf_302080214_120"},
        "provenance_place":   {"type": "combobox", "id": "dlf_302080215_120"},
    },
}

# Funder repeating set (Acquisition tab, _116 panel)
FUNDER_FIELDS = {
    "fieldset_legend": "Funder",
    "add_button":      "Add Another Set",
    "delete_button":   "Delete Set",
    "fields": {
        "funder":         {"type": "combobox", "id": "dlf_302080204_116"},
        "funding_amount": {"type": "text",     "id": "dlf_302080205_116"},
        "funding_type":   {"type": "combobox", "id": "dlf_302080206_116"},
    },
}

# ─────────────────────────────────────────────
# ADMINISTRATION TAB FIELDS (dlf_302090... prefix)
# Tab must be clicked before these fields are accessible.
# ─────────────────────────────────────────────
ADMIN_FIELDS = {
    # Status section (_121)
    "record_status":          {"type": "combobox", "id": "dlf_302090201_121"},
    "legal_ownership_status": {"type": "combobox", "id": "dlf_302090202_121"},
    "restriction_type":       {"type": "combobox", "id": "dlf_302090203_121"},
    # Loans and Exhibitions (_123) — textarea, not append-only in main script
    "loan_in_details":        {"type": "text",     "id": "dlf_302090209_123"},
    "loan_out_details":       {"type": "text",     "id": "dlf_302090210_123"},
    "exhibition_history":     {"type": "text",     "id": "dlf_302090211_123"},
    # General Flag / General Notes Admin (_125)
    "general_flag":           {"type": "combobox", "id": "dlf_302090226_125"},
    "general_notes_admin":    {"type": "text",     "id": "dlf_302090227_125"},
}

# Rights repeating set (Administration tab, _122 panel)
RIGHTS_FIELDS = {
    "fieldset_legend": "Rights",
    "add_button":      "Add Another Set",
    "delete_button":   "Delete Set",
    "fields": {
        "rights_expiry_date": {"type": "text",     "id": "dlf_302090207_122"},
        "rights_notes":       {"type": "text",     "id": "dlf_302090208_122"},
        "rights_owner":       {"type": "combobox", "id": "dlf_302090205_122"},
        "rights_start_date":  {"type": "text",     "id": "dlf_302090206_122"},
        "rights_type":        {"type": "combobox", "id": "dlf_302090204_122"},
    },
}

# Comments repeating set (Administration tab, _125 panel)
COMMENTS_FIELDS = {
    "fieldset_legend": "Comments",
    "add_button":      "Add Another Set",
    "delete_button":   "Delete Set",
    "fields": {
        "comments":        {"type": "text",     "id": "dlf_302090223_125"},
        "comments_date":   {"type": "text",     "id": "dlf_302090225_125"},
        "comments_person": {"type": "combobox", "id": "dlf_302090224_125"},
    },
}

# ─────────────────────────────────────────────
# OTHER DETAILS repeating sets (Detail Fields tab, _75 panel)
# These are on the Detail Fields tab but are repeating sets,
# so they use fill_repeating_set() rather than the simple field loop.
# ─────────────────────────────────────────────

# Other Maker Contributor repeating set — keyed by catalogue type
# All types share the fieldset legend "Other Maker Contributor" but have different dlf_ IDs.
OTHER_MAKER_FIELDS = {
    "archaeology": {
        "fieldset_legend": "Other Maker Contributor",
        "add_button":      "Add Another Set",
        "delete_button":   "Delete Set",
        "fields": {
            "other_maker":      {"type": "combobox", "id": "dlf_302050150_75"},
            "other_maker_role": {"type": "combobox", "id": "dlf_302050151_75"},
        },
    },
    "archive": {
        "fieldset_legend": "Other Maker Contributor",
        "add_button":      "Add Another Set",
        "delete_button":   "Delete Set",
        "fields": {
            "other_maker":      {"type": "combobox", "id": "dlf_302040141_62"},
            "other_maker_role": {"type": "combobox", "id": "dlf_302040142_62"},
        },
    },
    "photography": {
        "fieldset_legend": "Other Maker Contributor",
        "add_button":      "Add Another Set",
        "delete_button":   "Delete Set",
        "fields": {
            "other_maker":      {"type": "combobox", "id": "dlf_302030145_38"},
            "other_maker_role": {"type": "combobox", "id": "dlf_302030146_38"},
        },
    },
    "naturalscience": {
        "fieldset_legend": "Other Maker Contributor",
        "add_button":      "Add Another Set",
        "delete_button":   "Delete Set",
        "fields": {
            "other_maker":      {"type": "combobox", "id": "dlf_302070149_13"},
            "other_maker_role": {"type": "combobox", "id": "dlf_302070150_13"},
        },
    },
}

# Other Number repeating set - keyed by catalogue type
# Natural Science uses different IDs (_13) than other types (_75)
OTHER_NUMBER_FIELDS = {
    "archaeology": {
        "fieldset_legend": "Other Number",
        "add_button":      "Add Another Set",
        "delete_button":   "Delete Set",
        "fields": {
            "other_number":      {"type": "text",     "id": "dlf_500200252_75"},
            "other_number_type": {"type": "combobox", "id": "dlf_500200251_75"},
        },
    },
    "archive": {
        "fieldset_legend": "Other Number",
        "add_button":      "Add Another Set",
        "delete_button":   "Delete Set",
        "fields": {
            "other_number":      {"type": "text",     "id": "dlf_302040146_62"},
            "other_number_type": {"type": "combobox", "id": "dlf_302040147_62"},
        },
    },
    "photography": {
        "fieldset_legend": "Other Number",
        "add_button":      "Add Another Set",
        "delete_button":   "Delete Set",
        "fields": {
            "other_number":      {"type": "text",     "id": "dlf_302030150_38"},
            "other_number_type": {"type": "combobox", "id": "dlf_302030151_38"},
        },
    },
    "naturalscience": {
        "fieldset_legend": "Other Number",
        "add_button":      "Add Another Set",
        "delete_button":   "Delete Set",
        "fields": {
            "other_number":      {"type": "text",     "id": "dlf_302070151_13"},
            "other_number_type": {"type": "combobox", "id": "dlf_302070152_13"},
        },
    },
}

# ─────────────────────────────────────────────
# ITEM COUNT field IDs — keyed by catalogue type
# Detected from the URL path segment after /create/objects/
# ─────────────────────────────────────────────
ITEM_COUNT_IDS = {
    # Archaeology  (section _70)
    "archaeology":   {"item_count": "dlf_302050128_70", "item_count_notes": "dlf_302050129_70"},
    # Archive       (section _57)
    "archive":       {"item_count": "dlf_302040120_57", "item_count_notes": "dlf_302040121_57"},
    # Photography / Multimedia (section _32)
    "photography":   {"item_count": "dlf_302030119_32", "item_count_notes": "dlf_302030120_32"},
    # Natural Science (section _7)
    "naturalscience":{"item_count": "dlf_302070130_7",  "item_count_notes": "dlf_302070131_7"},
}

# ─────────────────────────────────────────────
# PART ID / PART DESCRIPTION field IDs — keyed by catalogue type
# Each entry: part_id dlf_, part_desc dlf_, fieldset legend text,
#             and the button label used to add more rows.
# ─────────────────────────────────────────────
PART_FIELDS = {
    # Archaeology uses "Part Holdings" / "Parts/Holdings" label
    "archaeology": {
        "part_id_dlf":   "dlf_500200250_70",
        "part_desc_dlf":  None,               # Archaeology Part Holdings has no description sub-field
        "fieldset_legend": "Part Holdings",
        "add_button":      "Add Another Set",
        "delete_button":   "Delete Set",
    },
    # Archive uses "Part Id" section with Part ID Number + Part Description
    "archive": {
        "part_id_dlf":    "dlf_302040122_57",
        "part_desc_dlf":  "dlf_302040123_57",
        "fieldset_legend": "Part Id",
        "add_button":      "Add Another Set",
        "delete_button":   "Delete Set",
    },
    # Photography uses "Part Id" section
    "photography": {
        "part_id_dlf":    "dlf_302030121_32",
        "part_desc_dlf":  "dlf_302030122_32",
        "fieldset_legend": "Part Id",
        "add_button":      "Add Another Set",
        "delete_button":   "Delete Set",
    },
    # Natural Science has no Part Holdings section — omitted intentionally.
}

# Subject & Association Keywords field IDs — keyed by catalogue type
KEYWORDS_CONFIG = {
    "archaeology":    {"base_id": "fieldTermComboBox-302050146_73_55", "fieldset": "#x-auto-363"},
    "archive":        {"base_id": "fieldTermComboBox-302040137_60_38", "fieldset": None},
    "photography":    {"base_id": "fieldTermComboBox-302030141_36_45", "fieldset": None},
    "naturalscience": {"base_id": "fieldTermComboBox-302070145_11_51", "fieldset": None},
}

# Field Collection Place Keywords — Natural Science only, same repeating structure
NS_PLACE_KEYWORDS_BASE_ID = "fieldTermComboBox-302070122_4_28"
NS_PLACE_KEYWORDS_LEGEND  = "Field Collection Place Keywords"

# Fallback (original default) — Archaeology
KEYWORDS_BASE_ID  = "fieldTermComboBox-302050146_73_55"
KEYWORDS_FIELDSET = "#x-auto-363"


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def val(row, key):
    """Return stripped string or empty string if blank/NaN."""
    v = row.get(key, "")
    return "" if pd.isna(v) else str(v).strip()


def split_semi(value):
    """Split a semicolon-separated string into a list of stripped non-empty values."""
    return [s.strip() for s in value.split(";") if s.strip()]


def detect_catalogue_type(url):
    """
    Infer catalogue type from the eHive edit URL.
    Returns one of: 'archaeology', 'archive', 'photography', 'naturalscience', or None.
    Many eHive URLs are numeric-only and don't contain the catalogue name,
    so this may return None — in that case the page heading is checked instead.
    """
    url_lower = url.lower()
    if "archaeology" in url_lower:
        return "archaeology"
    if "archive" in url_lower:
        return "archive"
    if "photography" in url_lower or "multimedia" in url_lower:
        return "photography"
    if "natural" in url_lower or "naturalscience" in url_lower:
        return "naturalscience"
    return None


async def detect_catalogue_type_from_page(page):
    """
    Fallback: read the page heading rendered by eHive (e.g. 'Natural Science',
    'Archaeology', 'Archive', 'Photography and Multimedia') to detect type.
    """
    try:
        heading = await page.locator(".page-heading").first.inner_text()
        heading_lower = heading.lower()
        if "archaeology" in heading_lower:
            return "archaeology"
        if "archive" in heading_lower:
            return "archive"
        if "photography" in heading_lower or "multimedia" in heading_lower:
            return "photography"
        if "natural" in heading_lower:
            return "naturalscience"
    except Exception:
        pass
    return None


def build_edit_url(object_url, account_id):
    """Convert object URL to edit URL."""
    object_url = object_url.strip().rstrip("/")
    if "/create/objects/" in object_url:
        return object_url
    if "/objects/" in object_url:
        return object_url.replace(
            f"/accounts/{account_id}/objects/",
            f"/accounts/{account_id}/create/objects/"
        )
    return object_url


# ─────────────────────────────────────────────
# TAB NAVIGATION
# ─────────────────────────────────────────────

async def click_tab(page, tab_name):
    """
    Click a GWT tab by its label text (e.g. 'Acquisition', 'Administration').
    Waits for the tab panel content to render before returning.
    GWT lazy-loads tab content, so we wait for a tab-specific dlf_ ID to appear.
    """
    # Map tab names to a dlf_ prefix unique to that tab's fields
    TAB_WAIT_SELECTORS = {
        "Acquisition":     "[id^='dlf_302080']",   # Acquisition tab fields
        "Administration":  "[id^='dlf_302090']",   # Administration tab fields
    }
    wait_selector = TAB_WAIT_SELECTORS.get(tab_name, "[id^='dlf_']")

    tab_label = page.locator("div.gwt-Label").filter(has_text=tab_name).first
    try:
        await tab_label.click()
        await asyncio.sleep(1.5)
        # Wait for a field specific to this tab to render
        await page.wait_for_selector(wait_selector, timeout=15000)
        await asyncio.sleep(1.0)
        print(f"  → Switched to {tab_name} tab")
    except Exception as e:
        print(f"  ⚠ Could not switch to {tab_name} tab: {e}")


# ─────────────────────────────────────────────
# FIELD FILLERS
# ─────────────────────────────────────────────

async def fill_text(page, dlf_id, value, append=False, label=None):
    """Fill a plain text input or textarea using stable dlf_ ID."""
    if not value:
        return False
    is_clear = value == CLEAR
    try:
        selector = f"[id^='{dlf_id}'] input, [id^='{dlf_id}'] textarea"
        element = page.locator(selector).first
        await element.wait_for(state="visible", timeout=15000)
        await element.scroll_into_view_if_needed()
        if is_clear:
            await element.fill("")
        elif append:
            existing = await element.input_value()
            if existing.strip():
                value = existing.strip() + "\n" + value.strip()
            await element.fill(value)
        else:
            await element.fill(value)
        tag = label or dlf_id
        print(f"  ✓ {tag}: {'[cleared]' if is_clear else value[:80]}")
        await asyncio.sleep(FIELD_DELAY)
        return True
    except Exception as e:
        print(f"  ⚠ fill {dlf_id}: {e}")
        return False


async def fill_text_by_exact_id(page, input_id, value):
    """Fill a text input by its exact element id (used for item_count whose id includes _0)."""
    if not value:
        return
    try:
        element = page.locator(f"input[id='{input_id}-input'], input[id='{input_id}_0-input']").first
        await element.fill(value)
        await asyncio.sleep(FIELD_DELAY)
    except Exception as e:
        print(f"  ⚠ fill exact id {input_id}: {e}")


async def fill_combobox(page, dlf_id, value, append=False, label=None):
    """Type into a GWT autocomplete combobox using stable dlf_ ID."""
    if not value:
        return False
    is_clear = value == CLEAR
    try:
        selector = f"[id^='{dlf_id}'] input"
        element = page.locator(selector).first
        await element.wait_for(state="visible", timeout=15000)
        await element.scroll_into_view_if_needed()
        if is_clear:
            await element.fill("")
            await asyncio.sleep(0.3)
            await page.keyboard.press("Tab")
        else:
            if not append:
                await element.fill("")
                await asyncio.sleep(0.3)
            await element.click()
            await asyncio.sleep(0.3)
            await element.type(value, delay=50)
            await asyncio.sleep(1.5)
            try:
                suggestion = page.locator(".x-combo-list-item").first
                await suggestion.click(timeout=3000)
            except Exception:
                await page.keyboard.press("Tab")
        tag = label or dlf_id
        print(f"  ✓ {tag}: {'[cleared]' if is_clear else value[:80]}")
        await asyncio.sleep(FIELD_DELAY)
        return True
    except Exception as e:
        print(f"  ⚠ combobox {dlf_id}: {e}")
        return False


async def fill_keywords(page, csv_value, cat_type, append=False):
    """
    Fill semicolon-separated keywords into repeating combobox lines.
    append=True  — adds after existing keywords
    append=False — deletes existing keywords and fills from scratch

    Scopes all button clicks to the specific Subject and Association Keywords
    fieldset by matching its legend text, avoiding strict-mode errors from
    other repeating fieldsets on the same page.
    """
    if not csv_value:
        return False

    cfg = KEYWORDS_CONFIG.get(cat_type, {"base_id": KEYWORDS_BASE_ID, "fieldset": KEYWORDS_FIELDSET})
    base_id = cfg["base_id"]

    # Scope to the Subject and Association Keywords fieldset by legend text
    kw_fieldset = page.locator("fieldset").filter(
        has=page.locator("legend span.x-fieldset-header-text", has_text="Subject and Association Keywords")
    )

    js = "Array.from(document.querySelectorAll('input[id^=\"" + base_id + "_\"]')).filter(i => i.value.trim() !== '').length"

    if csv_value == CLEAR:
        existing_count = await page.evaluate(js)
        print(f"  ✓ subject_keywords: [cleared] ({existing_count} existing removed)")
        for _ in range(existing_count):
            try:
                delete_btn = kw_fieldset.locator("button.x-btn-text").filter(has_text="Delete").first
                await delete_btn.click()
                await asyncio.sleep(0.5)
            except Exception:
                break
        return True

    keywords = split_semi(csv_value)
    existing_count = await page.evaluate(js)

    if append:
        start_index = existing_count
        print(f"  \u2192 Appending {len(keywords)} keyword(s) after {existing_count} existing")
    else:
        print(f"  \u2192 Deleting {existing_count} existing keyword row(s)...")
        for _ in range(existing_count):
            try:
                delete_btn = kw_fieldset.locator("button.x-btn-text").filter(has_text="Delete").first
                await delete_btn.click()
                await asyncio.sleep(0.5)
            except Exception:
                break
        start_index = 0
        print(f"  \u2713 subject_keywords: {csv_value[:80]}")

    for i, keyword in enumerate(keywords):
        line_num = start_index + i + 1
        selector = f"input[id='{base_id}_{line_num}-input']"

        if start_index + i > 0:
            add_btn = kw_fieldset.locator("button.x-btn-text").filter(has_text="Add Another Line")
            await add_btn.click()
            await asyncio.sleep(0.8)
            await page.wait_for_selector(selector, timeout=5000)

        await page.click(selector)
        await asyncio.sleep(0.5)
        await page.type(selector, keyword, delay=50)
        await asyncio.sleep(1.5)
        try:
            suggestion = page.locator(".x-combo-list-item").first
            await suggestion.click(timeout=3000)
        except Exception:
            await page.keyboard.press("Tab")
        await asyncio.sleep(0.3)
    return True


async def fill_place_keywords(page, csv_value, append=False):
    """
    Fill Field Collection Place Keywords (Natural Science only).
    Same repeating combobox structure as subject keywords.
    Semicolon-separated for multiple values, but typically a single entry.
    """
    if not csv_value:
        return False

    kw_fieldset = page.locator("fieldset").filter(
        has=page.locator(
            "legend span.x-fieldset-header-text",
            has_text=NS_PLACE_KEYWORDS_LEGEND
        )
    )

    try:
        count = await kw_fieldset.count()
        if count == 0:
            print(f"  ⚠ Field Collection Place Keywords fieldset not found — skipping")
            return False
    except Exception:
        return False

    base_id = NS_PLACE_KEYWORDS_BASE_ID
    js = "Array.from(document.querySelectorAll('input[id^=\"" + base_id + "_\"]')).filter(i => i.value.trim() !== '').length"
    existing_count = await page.evaluate(js)

    if csv_value == CLEAR:
        print(f"  ✓ field_collection_place_keywords: [cleared] ({existing_count} existing removed)")
        for _ in range(existing_count):
            try:
                delete_btn = kw_fieldset.locator("button.x-btn-text").filter(has_text="Delete").first
                await delete_btn.click()
                await asyncio.sleep(0.5)
            except Exception:
                break
        return True

    keywords = split_semi(csv_value)

    if append:
        start_index = existing_count
    else:
        for _ in range(existing_count):
            try:
                delete_btn = kw_fieldset.locator("button.x-btn-text").filter(has_text="Delete").first
                await delete_btn.click()
                await asyncio.sleep(0.5)
            except Exception:
                break
        start_index = 0
        print(f"  ✓ field_collection_place_keywords: {csv_value[:80]}")

    for i, keyword in enumerate(keywords):
        line_num = start_index + i + 1
        selector = f"input[id='{base_id}_{line_num}-input']"

        if start_index + i > 0:
            add_btn = kw_fieldset.locator("button.x-btn-text").filter(has_text="Add Another Line")
            await add_btn.click()
            await asyncio.sleep(0.8)
            await page.wait_for_selector(selector, timeout=5000)

        await page.click(selector)
        await asyncio.sleep(0.5)
        await page.type(selector, keyword, delay=50)
        await asyncio.sleep(1.5)
        try:
            suggestion = page.locator(".x-combo-list-item").first
            await suggestion.click(timeout=3000)
        except Exception:
            await page.keyboard.press("Tab")
        await asyncio.sleep(0.3)
    return True


async def fill_item_count(page, cat_type, item_count_val, item_count_notes_val, append=False):
    """Fill Item Count and Item Count Notes for the detected catalogue type."""
    ids = ITEM_COUNT_IDS.get(cat_type)
    if not ids:
        print(f"  ⚠ item_count: unknown catalogue type '{cat_type}', skipping")
        return False

    filled = False
    if item_count_val:
        if await fill_text(page, ids["item_count"], item_count_val, append=False, label="item_count"):
            filled = True
    if item_count_notes_val:
        if await fill_text(page, ids["item_count_notes"], item_count_notes_val, append, label="item_count_notes"):
            filled = True
    return filled


async def fill_parts(page, cat_type, part_ids_val, part_descs_val, append=False):
    """
    Fill Part ID (and optionally Part Description) repeating rows.
    part_ids_val  — semicolon-separated string of part IDs
    part_descs_val — semicolon-separated string of part descriptions (may be shorter)
    append=False  — deletes existing rows first
    append=True   — adds new rows after existing ones
    """
    if not part_ids_val:
        return False

    cfg = PART_FIELDS.get(cat_type)
    if not cfg:
        print(f"  ⚠ part_ids: catalogue type '{cat_type}' has no Part Holdings section — skipping")
        return False

    legend     = cfg["fieldset_legend"]
    del_btn    = cfg["delete_button"]
    fieldset_locator = page.locator("fieldset").filter(has_text=legend)

    if part_ids_val == CLEAR:
        existing_count = await fieldset_locator.locator(".x-border").count()
        print(f"  ✓ part_ids: [cleared] ({existing_count} existing rows removed)")
        for _ in range(existing_count):
            try:
                delete_btn_loc = fieldset_locator.locator("button.x-btn-text").filter(has_text=del_btn).first
                await delete_btn_loc.click()
                await asyncio.sleep(0.6)
            except Exception:
                break
        return True

    add_btn  = cfg["add_button"]
    id_dlf   = cfg["part_id_dlf"]
    desc_dlf = cfg["part_desc_dlf"]

    part_ids   = split_semi(part_ids_val)
    part_descs = split_semi(part_descs_val) if part_descs_val else []
    while len(part_descs) < len(part_ids):
        part_descs.append("")

    # Count existing rows (border-wrapped sub-divs inside the fieldset)
    existing_count = await fieldset_locator.locator(".x-border").count()

    if not append:
        for _ in range(existing_count):
            try:
                delete_btn_loc = fieldset_locator.locator("button.x-btn-text").filter(has_text=del_btn).first
                await delete_btn_loc.click()
                await asyncio.sleep(0.6)
            except Exception:
                break
        existing_count = 0

    print(f"  ✓ part_ids: {part_ids_val[:80]}")

    for i, (pid, pdesc) in enumerate(zip(part_ids, part_descs)):
        row_num = existing_count + i

        if row_num > 0:
            add_btn_loc = fieldset_locator.locator("button.x-btn-text").filter(has_text=add_btn).last
            await add_btn_loc.click()
            await asyncio.sleep(0.8)

        id_input = fieldset_locator.locator(f"[id^='{id_dlf}'] input").nth(row_num)
        try:
            await id_input.fill(pid)
            await asyncio.sleep(0.3)
        except Exception as e:
            print(f"  ⚠ part_id row {row_num}: {e}")

        if desc_dlf and pdesc:
            desc_input = fieldset_locator.locator(f"[id^='{desc_dlf}'] input, [id^='{desc_dlf}'] textarea").nth(row_num)
            try:
                await desc_input.fill(pdesc)
                await asyncio.sleep(0.3)
            except Exception as e:
                print(f"  ⚠ part_desc row {row_num}: {e}")

    await asyncio.sleep(FIELD_DELAY)
    return True


async def fill_repeating_set(page, row, config, append=False):
    """
    Fill a repeating set (Provenance, Funder, Rights, Comments) from CSV data.
    Only fills ONE new set per CSV row. If all sub-fields in the CSV are blank,
    skips the set entirely.

    config must have: fieldset_legend, add_button, delete_button, fields dict.
    Each field in fields: {csv_key: {"type": "text"|"combobox", "id": "dlf_..."}}.
    """
    legend  = config["fieldset_legend"]
    fields  = config["fields"]
    add_btn = config["add_button"]

    # Check if any CSV values are provided for this set
    values = {k: val(row, k) for k in fields}
    if not any(values.values()):
        return False

    print(f"  → Filling {legend} repeating set")

    # Locate the fieldset by its legend text
    fieldset_loc = page.locator("fieldset").filter(
        has=page.locator("legend span.x-fieldset-header-text", has_text=legend)
    )

    # Wait for the fieldset to be visible and stable
    try:
        await fieldset_loc.first.wait_for(state="visible", timeout=10000)
        await asyncio.sleep(0.5)  # Let it settle
    except Exception as e:
        print(f"  ⚠ {legend} fieldset not found or not visible: {e}")
        return

    # Check if the fieldset is collapsed and expand it if needed
    # Look for the collapse/expand toggle button in the legend
    try:
        legend_element = fieldset_loc.locator("legend").first
        # Scroll the fieldset into view
        await legend_element.scroll_into_view_if_needed()
        await asyncio.sleep(0.3)
        
        # Check if there's a collapse indicator (the fieldset might be collapsed)
        # Try to click the legend to expand it (some fieldsets are collapsible)
        is_collapsed = await fieldset_loc.locator(".x-fieldset-collapsed").count() > 0
        if is_collapsed:
            print(f"  → Expanding collapsed {legend} fieldset...")
            await legend_element.click()
            await asyncio.sleep(0.5)
    except Exception:
        pass  # Not collapsible or already expanded

    # Count existing sets
    existing_count = await fieldset_loc.locator(".x-border").count()

    if existing_count > 0 and not append:
        set_index = 0
    else:
        if existing_count > 0:
            try:
                add_btn_loc = fieldset_loc.locator("button.x-btn-text").filter(has_text=add_btn).last
                await add_btn_loc.click()
                await asyncio.sleep(1.0)
            except Exception as e:
                print(f"  ⚠ Could not click Add Another Set for {legend}: {e}")
                return False
        set_index = existing_count if existing_count > 0 else 0

    # Fill each sub-field in the set
    for csv_key, field_info in fields.items():
        value = values[csv_key]
        if not value:
            continue
        dlf_id = field_info["id"]
        ftype  = field_info["type"]
        try:
            if ftype == "text":
                selector = f"[id^='{dlf_id}'] input, [id^='{dlf_id}'] textarea"
                elements = fieldset_loc.locator(selector)
                if await elements.count() == 0:
                    print(f"  ⚠ {legend}.{csv_key}: element not found")
                    continue
                element = elements.nth(set_index)
                await element.wait_for(state="visible", timeout=15000)
                await element.scroll_into_view_if_needed()
                await element.click()
                await element.fill("", timeout=5000)
                await asyncio.sleep(0.2)
                await element.fill(value, timeout=5000)
                print(f"  ✓ {csv_key}: {value[:80]}")
                await asyncio.sleep(FIELD_DELAY)
            elif ftype == "combobox":
                selector = f"[id^='{dlf_id}'] input"
                elements = fieldset_loc.locator(selector)
                if await elements.count() == 0:
                    print(f"  ⚠ {legend}.{csv_key}: element not found")
                    continue
                element = elements.nth(set_index)
                await element.wait_for(state="visible", timeout=15000)
                await element.scroll_into_view_if_needed()
                await element.click(timeout=5000)
                await element.fill("", timeout=5000)
                await asyncio.sleep(0.3)
                await element.type(value, delay=50)
                await asyncio.sleep(1.5)
                try:
                    suggestion = page.locator(".x-combo-list-item").first
                    await suggestion.click(timeout=3000)
                except Exception:
                    await page.keyboard.press("Tab")
                print(f"  ✓ {csv_key}: {value[:80]}")
                await asyncio.sleep(FIELD_DELAY)
        except Exception as e:
            print(f"  ⚠ {legend}.{csv_key}: {e}")
    return True


async def has_tab_fields(row, field_dict, *repeating_configs):
    """Check if any CSV columns for a tab have values, to avoid unnecessary tab clicks."""
    for key in field_dict:
        if val(row, key):
            return True
    for config in repeating_configs:
        for key in config["fields"]:
            if val(row, key):
                return True
    return False


async def fill_related_acquisition_record(page, acq_number):
    """
    Set the Related Acquisition Record on the Acquisition tab.
    Workflow:
      1. If a relationship already exists → click Remove Relationship, wait for
         the Find Record button to reappear (indicates the UI has reset)
      2. Click Find Record → popup grid appears
      3. Use JS to locate the matching row, then Playwright to click it
         (JS .click() doesn't fire GWT's selection listener properly)
      4. Click OK → popup closes, relationship assigned
    """
    if not acq_number:
        return

    print(f"  → Setting Related Acquisition Record: {acq_number}")

    # Step 1: Remove existing relationship if present
    # The Remove Relationship button only exists when a record is already linked.
    # After clicking it, the Find Record button appears in its place.
    try:
        remove_btn = page.locator("#RemoveRelationshipButton button")
        if await remove_btn.count() > 0 and await remove_btn.is_visible():
            print("  → Removing existing acquisition relationship...")
            await remove_btn.click()
            # Wait for the Find Record button to appear (confirms removal complete)
            await page.wait_for_selector("#findAcqRelatedRecordsButton", state="visible", timeout=10000)
            await asyncio.sleep(1.0)
            print("  → Existing relationship removed")
    except Exception:
        pass  # No existing relationship — fine

    # Step 2: Click Find Record
    try:
        find_btn = page.locator("#findAcqRelatedRecordsButton button")
        await find_btn.click()
        await asyncio.sleep(2.0)
    except Exception as e:
        print(f"  ⚠ Could not click Find Record: {e}")
        return

    # Step 3: Wait for the popup grid to render
    try:
        await page.wait_for_selector(".x-grid3-col-acquisitionNumber", timeout=10000)
        await asyncio.sleep(1.0)
    except Exception:
        print("  ⚠ Find Record popup grid did not appear")
        return

    # Use JS to find the matching row's acquisitionNumber cell element,
    # then use Playwright's .click() on it so GWT registers the selection.
    cell_handle = await page.evaluate_handle("""
        (targetNum) => {
            const cells = [...document.querySelectorAll('.x-grid3-col-acquisitionNumber')];
            const cell = cells.find(c => c.textContent.trim() === targetNum);
            return cell || null;
        }
    """, acq_number)

    # Check if we got an element or null
    is_null = await page.evaluate("(el) => el === null", cell_handle)
    if is_null:
        print(f"  ⚠ Could not find acquisition record '{acq_number}' in the popup grid")
        try:
            cancel_btn = page.locator("button.x-btn-text").filter(has_text="Cancel")
            await cancel_btn.click()
            await asyncio.sleep(1.0)
        except Exception:
            pass
        return

    # Playwright click on the actual DOM element — this fires GWT events properly
    await cell_handle.as_element().click()
    await asyncio.sleep(1.0)

    print(f"  → Selected '{acq_number}' in grid")

    # Step 4: Click OK (should now be enabled after row selection)
    try:
        ok_btn = page.locator("button.x-btn-text").filter(has_text="OK").first
        # Wait briefly for it to become enabled
        await page.wait_for_function(
            """() => {
                const btns = [...document.querySelectorAll('button.x-btn-text')];
                const ok = btns.find(b => b.textContent.trim() === 'OK');
                return ok && ok.getAttribute('aria-disabled') !== 'true';
            }""",
            timeout=5000
        )
        await ok_btn.click()
        await asyncio.sleep(2.0)
        print(f"  → Acquisition record linked")
    except Exception as e:
        print(f"  ⚠ Could not click OK on Find Record popup: {e}")
        # Try force-closing the popup
        try:
            cancel_btn = page.locator("button.x-btn-text").filter(has_text="Cancel")
            await cancel_btn.click()
            await asyncio.sleep(1.0)
        except Exception:
            pass


# ─────────────────────────────────────────────
# SHARED HELPERS
# ─────────────────────────────────────────────

async def _check_session(page):
    """Return False if the browser has been redirected to the eHive login page."""
    if "log-in" in page.url.lower():
        print("\n" + "=" * 40)
        print("  SESSION EXPIRED — you have been logged out of eHive.")
        print("  The script cannot continue. Re-run and log in again.")
        print("=" * 40)
        return False
    return True


async def _save_record(page):
    """Click Save, confirm the popup, and verify the page left the edit view."""
    print("  → Saving...")
    await page.locator("#publishDraftButtonTop button").click()
    await page.wait_for_selector("#confirmPublishRecordButton", state="visible", timeout=15000)
    await asyncio.sleep(1)
    await page.locator("#confirmPublishRecordButton button").click(force=True)
    await asyncio.sleep(1)
    await page.wait_for_load_state("networkidle")
    await asyncio.sleep(1.5)
    if "/create/objects/" in page.url:
        print("  ⚠ Still on edit page after save — eHive may have shown a validation error")
        return False
    return True


async def _fill_all_fields(page, row, cat_type, append):
    """Fill every field from a CSV row. Returns True if at least one field was written."""
    any_filled = False

    # ── Standard fields ───────────────────────────────────────────────
    for field_key, field_info in get_fields(cat_type).items():
        value = val(row, field_key)
        if not value:
            continue
        if field_info["type"] == "text":
            if await fill_text(page, field_info["id"], value, append, label=field_key):
                any_filled = True
        elif field_info["type"] == "combobox":
            if await fill_combobox(page, field_info["id"], value, append, label=field_key):
                any_filled = True

    # ── Subject & Association Keywords ────────────────────────────────
    if await fill_keywords(page, val(row, "subject_keywords"), cat_type or "archaeology", append):
        any_filled = True

    # ── Field Collection Place Keywords (Natural Science only) ────────
    if cat_type == "naturalscience":
        if await fill_place_keywords(page, val(row, "field_collection_place_keywords"), append):
            any_filled = True

    # ── Item Count ────────────────────────────────────────────────────
    if cat_type:
        if await fill_item_count(page, cat_type, val(row, "item_count"), val(row, "item_count_notes"), append):
            any_filled = True

    # ── Part ID / Part Description ────────────────────────────────────
    if cat_type:
        if await fill_parts(page, cat_type, val(row, "part_ids"), val(row, "part_descriptions"), append):
            any_filled = True

    # ── Other Maker Contributor ───────────────────────────────────────
    if cat_type and cat_type in OTHER_MAKER_FIELDS:
        if await fill_repeating_set(page, row, OTHER_MAKER_FIELDS[cat_type], append):
            any_filled = True

    # ── Other Number ─────────────────────────────────────────────────
    if cat_type and cat_type in OTHER_NUMBER_FIELDS:
        if await fill_repeating_set(page, row, OTHER_NUMBER_FIELDS[cat_type], append):
            any_filled = True

    # ── Acquisition tab ──────────────────────────────────────────────
    acq_record_val = val(row, "related_acquisition_record")
    has_acq = await has_tab_fields(row, ACQUISITION_FIELDS, PROVENANCE_FIELDS, FUNDER_FIELDS) or acq_record_val
    if has_acq:
        await click_tab(page, "Acquisition")
        await fill_related_acquisition_record(page, acq_record_val)
        for field_key, field_info in ACQUISITION_FIELDS.items():
            value = val(row, field_key)
            if not value:
                continue
            if field_info["type"] == "text":
                if await fill_text(page, field_info["id"], value, append, label=field_key):
                    any_filled = True
            elif field_info["type"] == "combobox":
                if await fill_combobox(page, field_info["id"], value, append, label=field_key):
                    any_filled = True
        if await fill_repeating_set(page, row, PROVENANCE_FIELDS, append):
            any_filled = True
        if await fill_repeating_set(page, row, FUNDER_FIELDS, append):
            any_filled = True

    # ── Administration tab ───────────────────────────────────────────
    if await has_tab_fields(row, ADMIN_FIELDS, RIGHTS_FIELDS, COMMENTS_FIELDS):
        await click_tab(page, "Administration")
        for field_key, field_info in ADMIN_FIELDS.items():
            value = val(row, field_key)
            if not value:
                continue
            if field_info["type"] == "text":
                if await fill_text(page, field_info["id"], value, append, label=field_key):
                    any_filled = True
            elif field_info["type"] == "combobox":
                if await fill_combobox(page, field_info["id"], value, append, label=field_key):
                    any_filled = True
        if await fill_repeating_set(page, row, RIGHTS_FIELDS, append):
            any_filled = True
        if await fill_repeating_set(page, row, COMMENTS_FIELDS, append):
            any_filled = True

    return any_filled


# ─────────────────────────────────────────────
# MAIN RECORD UPDATER
# ─────────────────────────────────────────────

async def update_record(page, row, append=False, cat_type_override=None):
    """Navigate to a record's edit page and update fields from the CSV row.
    Returns True on success (including skip), False on failure."""

    object_url = val(row, "url")
    if not object_url:
        print("  ⚠ No URL found, skipping row")
        return False

    edit_url = build_edit_url(object_url, ACCOUNT_ID)
    print(f"→ Updating: {edit_url}")

    await page.goto(edit_url)

    if not await _check_session(page):
        raise RuntimeError("Session expired")

    try:
        await page.wait_for_selector("#gwt", timeout=30000)
    except Exception:
        print(f"  ✗ Page did not load (no #gwt container) — skipping")
        return False

    try:
        await page.wait_for_selector("[id^='dlf_']", timeout=40000)
    except Exception:
        print(f"  ✗ Form fields did not render — skipping")
        return False

    await asyncio.sleep(2.0)

    cat_type = cat_type_override or detect_catalogue_type(edit_url)
    if not cat_type:
        cat_type = await detect_catalogue_type_from_page(page)
    print(f"  Catalogue type: {cat_type}" if cat_type else
          "  ⚠ Could not detect catalogue type — item_count/part fields will be skipped")

    any_filled = await _fill_all_fields(page, row, cat_type, append)

    if not any_filled:
        print("  ─ No fields to update — skipping save\n")
        return True

    if not await _save_record(page):
        return False

    print(f"  ✓ Saved\n")
    return True


async def create_record(page, row, template_view_url, cat_type_override=None):
    """
    Create a new record by clicking 'Create a similar record' on the template
    view page, then filling fields from the CSV row (always replace mode).
    Returns the URL of the newly created record's edit page, or None on failure.
    """
    print(f"→ Creating new record from template...")

    await page.goto(template_view_url)

    if not await _check_session(page):
        raise RuntimeError("Session expired")

    try:
        await page.wait_for_selector("button.btn-create-similar-object", timeout=20000)
    except Exception:
        print(f"  ✗ Template view page did not load — skipping")
        return None

    await page.locator("button.btn-create-similar-object").click()

    try:
        await page.wait_for_selector("#gwt", timeout=30000)
        await page.wait_for_selector("[id^='dlf_']", timeout=40000)
    except Exception:
        print(f"  ✗ New record edit form did not load — skipping")
        return None

    await asyncio.sleep(2.0)
    new_edit_url = page.url
    print(f"  New record edit page: {new_edit_url}")

    cat_type = cat_type_override or detect_catalogue_type(new_edit_url)
    if not cat_type:
        cat_type = await detect_catalogue_type_from_page(page)
    print(f"  Catalogue type: {cat_type}" if cat_type else
          "  ⚠ Could not detect catalogue type — item_count/part fields will be skipped")

    await _fill_all_fields(page, row, cat_type, append=False)

    if not await _save_record(page):
        return None

    saved_url = page.url
    print(f"  ✓ Created: {saved_url}\n")
    return saved_url



def parse_args():
    parser = argparse.ArgumentParser(description="eHive Record Updater")
    parser.add_argument("--csv",        help="Path to CSV file (skips the CSV prompt)")
    parser.add_argument("--account-id", default=ACCOUNT_ID, help="eHive account ID")
    return parser.parse_args()


async def main():
    args = parse_args()
    account_id_to_use = args.account_id

    # ── Mode ─────────────────────────────────────────────────────────
    print("=" * 40)
    print("  What would you like to do?")
    print("    u = Update existing records (CSV needs a 'url' column)")
    print("    c = Create new records from a template")
    run_mode = input("  Enter u or c:\n> ").strip().lower()
    is_create = run_mode == "c"
    print(f"  Mode: {'CREATE new records' if is_create else 'UPDATE existing records'}")

    # ── CSV path ──────────────────────────────────────────────────────
    print("=" * 40)
    if args.csv:
        csv_path = args.csv
        print(f"CSV (from --csv): {csv_path}")
    else:
        user_path = input("Enter CSV path (or press Enter to use default):\n> ").strip()
        csv_path = user_path if user_path else CSV_PATH
    print(f"Loading CSV: {csv_path}\n")
    df = pd.read_csv(csv_path, dtype=str)

    # ── Progress file — lives next to the CSV ─────────────────────────
    progress_file = os.path.splitext(csv_path)[0] + ".completed.txt"
    completed_urls = set()
    if not is_create and os.path.exists(progress_file):
        with open(progress_file) as f:
            completed_urls = {line.strip() for line in f if line.strip()}
        if completed_urls:
            print(f"  Resuming: {len(completed_urls)} URL(s) already completed "
                  f"(loaded from {os.path.basename(progress_file)})")

    # ── Template URL (create mode only) ──────────────────────────────
    template_view_url = None
    if is_create:
        print("=" * 40)
        print("  Enter the VIEW URL of the template record to clone from.")
        print("  (e.g. https://my.ehive.com/accounts/203598/objects/2275083)")
        template_view_url = input("  Template URL:\n> ").strip()
        if not template_view_url:
            print("  ✗ No template URL provided — cannot run in Create mode.")
            return
        print(f"  Template: {template_view_url}")

    # ── Append / Replace (update mode only) ──────────────────────────
    append = False
    if not is_create:
        print("=" * 40)
        mode = input("  Append or Replace existing data? (a/r):\n> ").strip().lower()
        append = mode == "a"
        print(f"  Mode: {'APPEND — adding to existing data' if append else 'REPLACE — overwriting existing data'}")

    # ── Catalogue type ────────────────────────────────────────────────
    print("=" * 40)
    print("  Catalogue type for this CSV:")
    print("    1 = Archaeology")
    print("    2 = Archive")
    print("    3 = Natural Science")
    print("    4 = Photography / Multimedia")
    print("    (leave blank to auto-detect from each page)")
    cat_choice = input("  Enter number:\n> ").strip()
    cat_map = {"1": "archaeology", "2": "archive", "3": "naturalscience", "4": "photography"}
    cat_type_override = cat_map.get(cat_choice)
    if cat_type_override:
        print(f"  Catalogue type set to: {cat_type_override}")
    else:
        print(f"  Catalogue type will be auto-detected per record")
    print("=" * 40 + "\n")
    print(f"Found {len(df)} records to {'create' if is_create else 'update'}\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS)
        page = await browser.new_page()

        try:
            await page.goto("https://my.ehive.com/log-in")
            print("=" * 40)
            print("  Browser is open — please log in manually.")
            print("  Once logged in, come back here and")
            print("  press ENTER to start the automation.")
            print("=" * 40)
            input()

            success, skipped, fail = 0, 0, 0
            for idx, row in df.iterrows():
                object_url = val(row, "url")

                # ── Skip already-completed rows ───────────────────────
                if not is_create and object_url in completed_urls:
                    print(f"→ Skipping (already done): {object_url}")
                    skipped += 1
                    continue

                try:
                    if is_create:
                        result = await create_record(
                            page, row, template_view_url,
                            cat_type_override=cat_type_override,
                        )
                        if result is None:
                            fail += 1
                        else:
                            success += 1
                    else:
                        ok = await update_record(
                            page, row,
                            append=append,
                            cat_type_override=cat_type_override,
                        )
                        if ok:
                            success += 1
                            if object_url:
                                with open(progress_file, "a") as pf:
                                    pf.write(object_url + "\n")
                        else:
                            fail += 1
                except RuntimeError as e:
                    # Session expiry raises RuntimeError — stop the run
                    print(f"\n  ✗ Stopping: {e}")
                    break
                except Exception as e:
                    print(f"  ✗ Row {idx + 1} failed: {e}")
                    traceback.print_exc()
                    print()
                    fail += 1

            print("=" * 40)
            print(f"Done!  ✓ {success} {'created' if is_create else 'updated'}"
                  + (f"  ↷ {skipped} skipped" if skipped else "")
                  + (f"  ✗ {fail} failed" if fail else ""))
            print("=" * 40)

        except Exception as e:
            print("\n" + "=" * 40)
            print("CRITICAL ERROR - Something went wrong!")
            print("=" * 40)
            print(f"Error: {e}")
            traceback.print_exc()
            print("=" * 40)

        finally:
            print("\n\nBrowser is still open. Press ENTER to close it...")
            input()
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
