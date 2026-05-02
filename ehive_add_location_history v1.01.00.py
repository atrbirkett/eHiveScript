"""
eHive Location History & Loans Updater  v1.01.00
===================================================
Automates adding a new Location History entry to existing eHive object records
from a CSV file. Always adds a NEW set (never overwrites existing entries).
Supports all four catalogue types — auto-detects which one is loaded.

Optionally also appends Loan In Details, Loan Out Details, and Exhibition
History on the Administration tab (append-only — never erases existing content).

Catalogue types supported:
    Archaeology       — fieldTermComboBox-500201298_139_36_N
    Archive           — fieldTermComboBox-500201293_139_20_N
    Natural Science   — fieldTermComboBox-500201303_139_33_N
    Photography       — fieldTermComboBox-500201292_139_22_N

Requirements:
    pip install playwright pandas
    playwright install chromium

Usage:
    1. Run: python ehive_add_location_history.py
    2. Answer the prompt for CSV path
    3. Log in manually in the browser window that opens
    4. Press Enter in the terminal to start the automation

CSV columns (leave any cell blank to skip that field):
    url                     — eHive object URL (required)
    location_history        — controlled term for the location (combobox)
    location_history_date   — date for the location entry (plain text)
    location_history_notes  — notes for the location entry (plain text)
    loan_in_details         — text to APPEND to Loan In Details (Administration tab)
    loan_out_details        — text to APPEND to Loan Out Details (Administration tab)
    exhibition_history      — text to APPEND to Exhibition History (Administration tab)

Fill order (reverse, so combobox popup fires last):
    1. Click "Add Another Set" (located by stable fieldset heading)
    2. Click new combobox → Tab x3 → Notes → type
    3. Shift+Tab x1 → Date → type
    4. Shift+Tab x2 → Combobox → type location → confirm autocomplete
    5. Popup "Update Current Location?" fires → click Yes
    6. If loan/exhibition columns have values → switch to Administration tab → append
    7. Save
"""

import pandas as pd
import asyncio
from playwright.async_api import async_playwright

# ─────────────────────────────────────────────
# CONFIGURATION — edit these before running
# ─────────────────────────────────────────────
ACCOUNT_ID  = "203598"
CSV_PATH    = r"C:\Users\ab1426\OneDrive - University of Bristol\Desktop\ehive\location_history_test.csv"

HEADLESS    = False
FIELD_DELAY = 0.5
# ─────────────────────────────────────────────

# Combobox ID prefixes for each catalogue type (N increments per set added)
CATALOGUE_COMBOBOX_PREFIXES = {
    "archaeology":    "fieldTermComboBox-500201298_139_36_",
    "archive":        "fieldTermComboBox-500201293_139_20_",
    "natural_science":"fieldTermComboBox-500201303_139_33_",
    "photography":    "fieldTermComboBox-500201292_139_22_",
}

# Loans and Exhibitions fields on the Administration tab (append-only textareas)
LOAN_EXHIBITION_FIELDS = {
    "loan_in_details":    "dlf_302090209_123",
    "loan_out_details":   "dlf_302090210_123",
    "exhibition_history": "dlf_302090211_123",
}


def val(row, key):
    """Return stripped string or empty string if blank/NaN."""
    v = row.get(key, "")
    return "" if pd.isna(v) else str(v).strip()


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


async def detect_catalogue_and_prefix(page):
    """
    Detect which catalogue type is loaded by checking which combobox prefix exists.
    Returns (catalogue_name, combobox_prefix) or raises if not found.
    """
    for cat_name, prefix in CATALOGUE_COMBOBOX_PREFIXES.items():
        selector = f"input[id^='{prefix}']"
        count = await page.evaluate(
            f"document.querySelectorAll(\"input[id^='{prefix}']\").length"
        )
        if count > 0:
            return cat_name, prefix
    raise RuntimeError("Could not detect catalogue type — no known Location History combobox found.")


async def click_tab(page, tab_name):
    """
    Click a GWT tab by its label text (e.g. 'Administration').
    Waits for the tab panel content to render before returning.
    """
    tab_label = page.locator("div.gwt-Label").filter(has_text=tab_name).first
    try:
        await tab_label.click()
        await asyncio.sleep(1.5)
        await page.wait_for_selector("[id^='dlf_']", timeout=15000)
        await asyncio.sleep(1.0)
        print(f"  → Switched to {tab_name} tab")
    except Exception as e:
        print(f"  ⚠ Could not switch to {tab_name} tab: {e}")


async def append_to_textarea(page, dlf_id, new_text):
    """
    Append text to an existing textarea field (never erases).
    Reads existing content, adds a newline separator if needed, then writes back.
    """
    if not new_text:
        return
    try:
        selector = f"[id^='{dlf_id}'] textarea"
        element = page.locator(selector).first
        existing = await element.input_value()
        if existing.strip():
            combined = existing.strip() + "\n" + new_text.strip()
        else:
            combined = new_text.strip()
        await element.fill(combined)
        await asyncio.sleep(0.5)
    except Exception as e:
        print(f"  ⚠ append {dlf_id}: {e}")


async def add_location_history(page, row):
    """
    Navigate to a record's edit page and add a new Location History set.
    Auto-detects catalogue type to use the correct combobox prefix.
    Fills in reverse order (Notes → Date → Combobox) so the popup fires last.
    """
    object_url = val(row, "url")
    if not object_url:
        print("  ⚠ No URL found, skipping row")
        return

    edit_url = build_edit_url(object_url, ACCOUNT_ID)
    print(f"→ Updating: {edit_url}")

    await page.goto(edit_url)
    await page.wait_for_load_state("networkidle")

    # ── Wait for form load — any known Location History combobox pattern ──
    try:
        await page.wait_for_selector(
            "input[id*='_139_']",
            timeout=20000
        )
    except Exception:
        print("  ✗ Form did not load (Location History section not found) — skipping")
        return

    await asyncio.sleep(1.5)

    # ── Auto-detect catalogue type ──
    try:
        cat_name, prefix = await detect_catalogue_and_prefix(page)
        print(f"  → Catalogue type: {cat_name.replace('_', ' ').title()}")
    except RuntimeError as e:
        print(f"  ✗ {e} — skipping")
        return

    # ── Count existing sets to calculate the new set number ──
    count_before = await page.evaluate(
        f"document.querySelectorAll(\"input[id^='{prefix}']\").length"
    )
    new_set_num = count_before + 1
    print(f"  → {count_before} existing set(s) — will add set {new_set_num}")

    # ── Click "Add Another Set" — locate by the Location History panel heading ──
    # The button is always inside the panel whose header contains
    # "Location History - use the Add Another Set button"
    # We use JavaScript to find it reliably regardless of dynamic x-auto IDs.
    clicked = await page.evaluate("""
        (() => {
            const spans = [...document.querySelectorAll('span.x-panel-header-text')];
            const header = spans.find(s => s.textContent.includes('Location History - use the Add Another Set'));
            if (!header) return false;
            const panel = header.closest('.x-panel');
            if (!panel) return false;
            const buttons = [...panel.querySelectorAll('button.x-btn-text')];
            const btn = buttons.find(b => b.textContent.trim() === 'Add Another Set');
            if (!btn) return false;
            btn.click();
            return true;
        })()
    """)

    if not clicked:
        print("  ✗ Could not find 'Add Another Set' button in Location History panel — skipping")
        return

    print("  → Clicked 'Add Another Set'")
    await asyncio.sleep(1.0)

    # ── Wait for the new combobox to appear ──
    new_location_selector = f"input[id='{prefix}{new_set_num}-input']"
    try:
        await page.wait_for_selector(new_location_selector, timeout=8000)
    except Exception:
        print(f"  ⚠ New set combobox (set {new_set_num}) did not appear — skipping fill")
        return

    # ── Click combobox, then Tab x3 to reach Notes field ──
    # Tab x1 → Term Pick List button
    # Tab x1 → Location History Date
    # Tab x1 → Location History Notes
    await page.click(new_location_selector)
    await asyncio.sleep(0.3)
    for _ in range(3):
        await page.keyboard.press("Tab")
        await asyncio.sleep(0.2)

    # ── Now on Location History Notes — type value ──
    notes_value = val(row, "location_history_notes")
    if notes_value:
        print(f"  → Filling notes: {notes_value}")
        await page.keyboard.type(notes_value, delay=30)
        await asyncio.sleep(FIELD_DELAY)

    # ── Shift+Tab x1 → Location History Date ──
    await page.keyboard.press("Shift+Tab")
    await asyncio.sleep(0.3)

    # ── Now on Location History Date — type value ──
    date_value = val(row, "location_history_date")
    if date_value:
        print(f"  → Filling date: {date_value}")
        await page.keyboard.type(date_value, delay=30)
        await asyncio.sleep(FIELD_DELAY)

    # ── Shift+Tab x2 → back to Location History combobox ──
    # Shift+Tab x1 → Term Pick List button (skip)
    # Shift+Tab x1 → Location History combobox
    await page.keyboard.press("Shift+Tab")
    await asyncio.sleep(0.2)
    await page.keyboard.press("Shift+Tab")
    await asyncio.sleep(0.3)

    # ── Fill Location History combobox — confirmation triggers the popup ──
    location_value = val(row, "location_history")
    if location_value:
        print(f"  → Filling location: {location_value}")
        await page.fill(new_location_selector, "")
        await page.type(new_location_selector, location_value, delay=50)
        await asyncio.sleep(1.5)
        # Confirm with first autocomplete suggestion — popup fires here
        try:
            await page.locator(".x-combo-list-item").first.click(timeout=3000)
        except Exception:
            await page.keyboard.press("Tab")
        await asyncio.sleep(0.5)

    # ── Popup fires after combobox value confirmed — always click Yes ──
    yes_button = page.locator("button.x-btn-text:has-text('Yes')")
    try:
        await yes_button.wait_for(state="visible", timeout=5000)
        print("  → 'Update Current Location?' popup — clicking Yes...")
        await yes_button.click()
        await asyncio.sleep(1.0)
    except Exception:
        print("  → No popup appeared — continuing...")

    # ── Loan / Exhibition fields (Administration tab, append-only) ────
    loan_in  = val(row, "loan_in_details")
    loan_out = val(row, "loan_out_details")
    exhibit  = val(row, "exhibition_history")

    if loan_in or loan_out or exhibit:
        await click_tab(page, "Administration")
        if loan_in:
            print(f"  → Appending Loan In Details")
            await append_to_textarea(page, LOAN_EXHIBITION_FIELDS["loan_in_details"], loan_in)
        if loan_out:
            print(f"  → Appending Loan Out Details")
            await append_to_textarea(page, LOAN_EXHIBITION_FIELDS["loan_out_details"], loan_out)
        if exhibit:
            print(f"  → Appending Exhibition History")
            await append_to_textarea(page, LOAN_EXHIBITION_FIELDS["exhibition_history"], exhibit)

    # ── Save ─────────────────────────────────────────────────────────
    print("  → Clicking Save...")
    await page.locator("#publishDraftButtonTop button").click()

    print("  → Waiting for save confirmation popup...")
    await page.wait_for_selector("#confirmPublishRecordButton", state="visible", timeout=15000)
    await asyncio.sleep(1)
    print("  → Clicking OK on popup...")
    await page.locator("#confirmPublishRecordButton button").click(force=True)
    await asyncio.sleep(1)
    await page.wait_for_load_state("networkidle")
    await asyncio.sleep(1.5)
    print(f"  ✓ Saved\n")


async def main():
    # Ask for CSV path
    user_path = input("Enter CSV path (or press Enter to use default):\n> ").strip()
    csv_path = user_path if user_path else CSV_PATH
    print(f"\nLoading CSV: {csv_path}\n")
    df = pd.read_csv(csv_path, dtype=str)

    print(f"Found {len(df)} records to update\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS)
        page = await browser.new_page()

        await page.goto("https://my.ehive.com/log-in")
        print("=" * 40)
        print("  Browser is open — please log in manually.")
        print("  Once logged in, come back here and")
        print("  press ENTER to start the automation.")
        print("=" * 40)
        input()

        success, fail = 0, 0
        for idx, row in df.iterrows():
            try:
                await add_location_history(page, row)
                success += 1
            except Exception as e:
                print(f"  ✗ Row {idx + 1} failed: {e}\n")
                fail += 1

        print("=" * 40)
        print(f"Done!   ✓ {success} updated   ✗ {fail} failed")
        print("=" * 40)
        input("\nPress ENTER to close the browser...")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
