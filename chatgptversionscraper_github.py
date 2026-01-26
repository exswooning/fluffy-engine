import os
import datetime
import time
import random
import re

from dotenv import load_dotenv

from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager

from google.oauth2.service_account import Credentials
import gspread

# --------------------------------------------------------------------
# Config
# --------------------------------------------------------------------
WEBSITE_URL = "http://std.nest.net.np/"
CREDENTIALS_FILE = "credentials.json"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:118.0) Gecko/20100101 Firefox/118.0",
]

ALL_SALES_SHEET = "All Sales"
METADATA_SHEET = "Meta"
GITHUB_STATUS_CELL = "A2"
GITHUB_STATUS_OK = "OK"
GITHUB_STATUS_FAIL = "FAIL"


# --------------------------------------------------------------------
# Google Sheets helpers
# --------------------------------------------------------------------
def authenticate_google():
    try:
        creds = Credentials.from_service_account_file(
            CREDENTIALS_FILE,
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
        gc = gspread.authorize(creds)
        print("✓ Google authentication successful.")
        return gc
    except Exception as e:
        print(f"❌ Google authentication failed: {e}")
        return None


def get_or_create_worksheet(spreadsheet, title, headers=None, rows=1000, cols=20):
    try:
        ws = spreadsheet.worksheet(title)
        return ws
    except gspread.WorksheetNotFound:
        print(f"Worksheet '{title}' not found. Creating...")
        ws = spreadsheet.add_worksheet(title=title, rows=str(rows), cols=str(cols))
        if headers:
            ws.append_row(headers)
        return ws


def read_github_status(gc, sheet_id):
    try:
        spreadsheet = gc.open_by_key(sheet_id)
        meta = get_or_create_worksheet(
            spreadsheet, METADATA_SHEET, headers=["Key", "Value"], rows=10, cols=2
        )
        values = meta.get_all_values()
        if len(values) >= 2 and len(values[1]) >= 2 and values[1][0] == "github_status":
            status = values[1][1]
            print(f"GitHub status from sheet: {status}")
            return status
        else:
            print("GitHub status not initialized in sheet.")
            return None
    except Exception as e:
        print(f"⚠️ Could not read GitHub status: {e}")
        return None


def write_github_status(gc, sheet_id, status):
    try:
        spreadsheet = gc.open_by_key(sheet_id)
        meta = get_or_create_worksheet(
            spreadsheet, METADATA_SHEET, headers=["Key", "Value"], rows=10, cols=2
        )
        values = meta.get_all_values()
        if len(values) < 2:
            meta.update("A1:B1", [["Key", "Value"]])
            meta.update("A2:B2", [["github_status", status]])
        else:
            meta.update("A2:B2", [["github_status", status]])
        print(f"GitHub status updated to: {status}")
    except Exception as e:
        print(f"⚠️ Could not write GitHub status: {e}")


# --------------------------------------------------------------------
# Selenium setup
# --------------------------------------------------------------------
def setup_driver():
    print("Setting up stealth browser driver...")
    options = webdriver.ChromeOptions()

    user_agent = random.choice(USER_AGENTS)
    options.add_argument(f"user-agent={user_agent}")
    print(f"  > Using User-Agent: {user_agent}")

    proxy_url = os.getenv("PROXY_URL")
    if proxy_url:
        options.add_argument(f"--proxy-server={proxy_url}")
        print("  > Using proxy server to mask IP.")

    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--ignore-certificate-errors")

    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    try:
        service = ChromeService(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        return driver
    except Exception as e:
        print(f"❌ WebDriver setup failed: {e}")
        return None


# --------------------------------------------------------------------
# Extraction
# --------------------------------------------------------------------
def extract_sales_data(driver):
    """
    Extract all names, invoices, amounts, and dates.

    Returns a list of dicts:
    { name, invoice, amount, date, full_text }
    """
    all_sales_data = []

    time.sleep(random.uniform(1, 3))

    print(f"Opening {WEBSITE_URL} ...")
    try:
        driver.get(WEBSITE_URL)
    except Exception as e:
        print(f"❌ driver.get failed: {e}")
        return []

    wait = WebDriverWait(driver, 30)
    print("Waiting for leaderboard cards...")

    try:
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.p-4")))
    except TimeoutException:
        print("❌ Timeout waiting for any leaderboard card.")
        print("Page title:", driver.title)
        print("Page length:", len(driver.page_source))
        return []

    time.sleep(random.uniform(2, 4))

    print("Simulating human-like scrolling...")
    for _ in range(random.randint(1, 2)):
        driver.execute_script(f"window.scrollBy(0, {random.randint(200, 500)});")
        time.sleep(random.uniform(0.5, 1.0))

    entries = driver.find_elements(By.CSS_SELECTOR, "div.p-4")
    print(f"Found {len(entries)} potential leaderboard entries.")

    if not entries:
        return []

    indices = list(range(len(entries)))
    random.shuffle(indices)

    sale_pattern = r"Sale of Rs\.?\s*([\d,]+\.?\d*)"
    invoice_pattern = r"Invoice ID:\s*#?(\d+)"
    date_pattern = r"Date:\s*([0-9]{4}-[0-9]{2}-[0-9]{2})"

    for i in indices:
        try:
            entries = driver.find_elements(By.CSS_SELECTOR, "div.p-4")
            if i >= len(entries):
                continue

            entry = entries[i]
            full_text = entry.text.strip()
            if not full_text:
                continue

            first_line = full_text.split("\n")[0]
            name_match = re.search(r"#\d+\s+(.+)", first_line)
            name = name_match.group(1).strip() if name_match else "Unknown"

            print(f"\n--- Processing: {name} (index {i}) ---")

            initial_len = len(full_text)
            actions = ActionChains(driver)
            actions.move_to_element(entry).pause(
                random.uniform(0.2, 0.6)
            ).click().perform()

            try:
                wait.until(
                    lambda d: len(
                        d.find_elements(By.CSS_SELECTOR, "div.p-4")[i].text
                    )
                    > initial_len
                )
                print("  ✓ Entry expanded.")
            except TimeoutException:
                print("  ⚠️ Expansion timeout; using existing text.")

            expanded_entries = driver.find_elements(By.CSS_SELECTOR, "div.p-4")
            expanded_text = (
                expanded_entries[i].text if i < len(expanded_entries) else full_text
            )

            sale_amounts = re.findall(sale_pattern, expanded_text, re.IGNORECASE)
            invoices = re.findall(invoice_pattern, expanded_text, re.IGNORECASE)
            dates = re.findall(date_pattern, expanded_text, re.IGNORECASE)

            if not sale_amounts or not invoices:
                print("  ⚠️ No detailed sales; storing raw text.")
                all_sales_data.append(
                    {
                        "name": name,
                        "invoice": "N/A",
                        "amount": "N/A",
                        "date": "N/A",
                        "full_text": expanded_text,
                    }
                )
                continue

            max_records = min(len(sale_amounts), len(invoices))
            for idx in range(max_records):
                amount_raw = sale_amounts[idx]
                invoice_id = invoices[idx]
                amount_clean = amount_raw.replace(",", "")

                if dates and idx < len(dates):
                    date_str = dates[idx]
                else:
                    date_str = datetime.datetime.utcnow().strftime("%Y-%m-%d")

                all_sales_data.append(
                    {
                        "name": name,
                        "invoice": invoice_id,
                        "amount": amount_clean,
                        "date": date_str,
                        "full_text": expanded_text,
                    }
                )
                print(
                    f"  ✓ Sale: Name={name}, Rs.{amount_clean}, Invoice #{invoice_id}, Date={date_str}"
                )

        except Exception as e:
            print(f"  ❌ Error processing entry index {i}: {e}")

    print(f"\nTotal extracted records: {len(all_sales_data)}")
    return all_sales_data


# --------------------------------------------------------------------
# Sheets update
# --------------------------------------------------------------------
def update_spreadsheet(gc, sheet_id, sales_data):
    if not sales_data:
        print("No new data to upload.")
        return

    try:
        print(f"Opening Google Sheet {sheet_id} ...")
        spreadsheet = gc.open_by_key(sheet_id)

        ws = get_or_create_worksheet(
            spreadsheet,
            ALL_SALES_SHEET,
            headers=[
                "Timestamp",
                "Name",
                "Invoice ID",
                "Amount",
                "Sale Date",
                "Full Scraped Text",
            ],
            rows=1000,
            cols=10,
        )

        existing = ws.get_all_values()
        existing_keys = set()
        for row in existing[1:]:
            if len(row) >= 5:
                key = f"{row[1]}|{row[2]}|{row[4]}"
                existing_keys.add(key)

        unique_sales = []
        for s in sales_data:
            key = f"{s['name']}|{s['invoice']}|{s['date']}"
            if key not in existing_keys:
                unique_sales.append(s)

        if not unique_sales:
            print("No new unique sales to add.")
            return

        print(f"Preparing {len(unique_sales)} unique rows for upload...")
        rows_to_append = []
        ts = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

        for s in unique_sales:
            rows_to_append.append(
                [
                    ts,
                    s["name"],
                    s["invoice"],
                    s["amount"],
                    s["date"],
                    s["full_text"],
                ]
            )

        ws.append_rows(rows_to_append, value_input_option="USER_ENTERED")
        print(f"🎉 SUCCESS: Appended {len(unique_sales)} new rows to '{ALL_SALES_SHEET}'!")

    except Exception as e:
        print(f"❌ Failed to update spreadsheet: {e}")


# --------------------------------------------------------------------
# Main with internal retries + GitHub/local logic
# --------------------------------------------------------------------
def run_once(gc, sheet_id, run_context):
    """Run one scraping attempt; return True on success, False on failure."""
    driver = setup_driver()
    if not driver:
        return False

    success = False
    try:
        sales_data = extract_sales_data(driver)
        if sales_data:
            update_spreadsheet(gc, sheet_id, sales_data)
            success = True
        else:
            print("No sales data extracted.")
            success = False
    finally:
        try:
            driver.quit()
        except Exception:
            pass

    return success


def main():
    print("\n======== Starting Stealth Scraper (with retries) ========")
    load_dotenv()
    sheet_id = os.getenv("GOOGLE_SHEET_ID")
    if not sheet_id:
        print("Error: GOOGLE_SHEET_ID not found.")
        return

    run_context = os.getenv("RUN_CONTEXT", "LOCAL").upper()
    print(f"Run context: {run_context}")

    gc = authenticate_google()
    if not gc:
        return

    # Coordination with GitHub
    if run_context != "GITHUB":
        status = read_github_status(gc, sheet_id)
        if status in (None, GITHUB_STATUS_OK):
            print("GitHub status is OK/unknown; backup will not run.")
            if run_context != "FORCE_LOCAL":
                print("\n======== Script Finished (backup not triggered) ========")
                return
        else:
            print("GitHub status is FAIL; running local backup.")

    max_attempts = 3
    delay_base = 5  # seconds

    any_success = False
    for attempt in range(1, max_attempts + 1):
        print(f"\n--- Attempt {attempt}/{max_attempts} ---")
        success = run_once(gc, sheet_id, run_context)
        if success:
            any_success = True
            print("Attempt succeeded.")
            break
        else:
            if attempt < max_attempts:
                delay = delay_base * attempt
                print(f"Attempt failed, retrying in {delay}s...")
                time.sleep(delay)
            else:
                print("All attempts failed.")

    if run_context == "GITHUB":
        write_github_status(gc, sheet_id, GITHUB_STATUS_OK if any_success else GITHUB_STATUS_FAIL)

    print("\n======== Script Finished ========")


if __name__ == "__main__":
    main()
