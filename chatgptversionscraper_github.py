import os
import datetime
import time
import random
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.action_chains import ActionChains
from webdriver_manager.chrome import ChromeDriverManager
from google.oauth2.service_account import Credentials
import gspread
import re

# --- Configuration ---
WEBSITE_URL = "http://std.nest.net.np/"
CREDENTIALS_FILE = "credentials.json"

# --- STEALTH: List of realistic, current browser User-Agents to rotate ---
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/118.0',
]

def authenticate_google():
    """Authenticates with Google Sheets using service account credentials."""
    try:
        creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=["https://www.googleapis.com/auth/spreadsheets"])
        gc = gspread.authorize(creds)
        print("✓ Google authentication successful.")
        return gc
    except Exception as e:
        print(f"❌ Google authentication failed: {e}")
        return None

def setup_driver():
    """Sets up a headless Chrome driver with enhanced stealth options."""
    print("Setting up stealth browser driver...")
    options = webdriver.ChromeOptions()
    
    # --- STEALTH: Rotate User-Agent ---
    user_agent = random.choice(USER_AGENTS)
    options.add_argument(f'user-agent={user_agent}')
    print(f"  > Using User-Agent: {user_agent}")
    
    # --- STEALTH: Use a proxy if available ---
    proxy_url = os.getenv("PROXY_URL")
    if proxy_url:
        options.add_argument(f'--proxy-server={proxy_url}')
        print("  > Using proxy server to mask IP.")

    # --- STEALTH: Common options to avoid detection ---
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    try:
        service = ChromeService(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        # --- STEALTH: Spoof the navigator.webdriver property ---
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return driver
    except Exception as e:
        print(f"❌ WebDriver setup failed: {e}")
        return None

def extract_sales_data(driver):
    """Navigates, humanizes interactions, and extracts sales data."""
    all_sales_data = []
    
    # --- HUMANIZING: Random initial delay before visiting site ---
    time.sleep(random.uniform(3, 8))
    
    driver.get(WEBSITE_URL)
    wait = WebDriverWait(driver, 20)
    
    print("Waiting for leaderboard to load...")
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.p-4.transition")))
    time.sleep(random.uniform(4, 7)) # Human-like pause after page load

    # --- HUMANIZING: Simulate random scrolling ---
    print("Simulating human-like scrolling...")
    for _ in range(random.randint(1, 3)):
        scroll_amount = random.randint(200, 500)
        driver.execute_script(f"window.scrollBy(0, {scroll_amount});")
        time.sleep(random.uniform(0.5, 1.5))

    leaderboard_entries = driver.find_elements(By.CSS_SELECTOR, "div.p-4.transition")
    print(f"Found {len(leaderboard_entries)} leaderboard entries.")

    # --- HUMANIZING: Process entries in a random order ---
    entry_indices = list(range(len(leaderboard_entries)))
    random.shuffle(entry_indices)

    for i in entry_indices:
        try:
            # Re-find elements to avoid stale references
            entry = driver.find_elements(By.CSS_SELECTOR, "div.p-4.transition")[i]
            
            # --- FIXED NAME EXTRACTION ---
            full_text = entry.text
            name_match = re.search(r'#\d+\s+(.+)', full_text.split('\n')[0])
            name = name_match.group(1).strip() if name_match else "Unknown"

            if name == "Unknown": continue

            print(f"\n--- Processing: {name} ---")
            initial_text_length = len(full_text)
            
            # --- HUMANIZING: Simulate complex mouse movement before clicking ---
            actions = ActionChains(driver)
            actions.move_to_element(entry).pause(random.uniform(0.3, 0.7)).click().perform()
            
            # Wait for content to expand
            wait.until(lambda d: len(d.find_elements(By.CSS_SELECTOR, "div.p-4.transition")[i].text) > initial_text_length)
            print(f"  ✓ Entry for {name} expanded.")
            
            expanded_text = driver.find_elements(By.CSS_SELECTOR, "div.p-4.transition")[i].text
            sales_pattern = r"Sale of Rs\.?\s*([\d,]+\.?\d*).*?Invoice ID:\s*#?(\d+)"
            matches = re.findall(sales_pattern, expanded_text, re.IGNORECASE)
            
            if not matches:
                print(f"  ⚠️ No detailed sales found for {name}.")
                continue

            for amount, invoice_id in matches:
                clean_amount = amount.replace(',', '')
                sale_record = {'name': name, 'amount': clean_amount, 'invoice': invoice_id}
                all_sales_data.append(sale_record)
                print(f"  ✓ Extracted Sale: Amount=Rs.{clean_amount}, Invoice=#{invoice_id}")
        
        except TimeoutException:
            print(f"  ❌ Timed out waiting for an entry to expand. Skipping.")
        except Exception as e:
            print(f"  ❌ An error occurred processing an entry: {e}")
            
    return all_sales_data

def update_spreadsheet(gc, sheet_id, sales_data):
    """Updates the Google Sheet with new, unique sales data."""
    if not sales_data:
        print("No new data to upload.")
        return
    try:
        print("Opening Google Sheet...")
        worksheet = gc.open_by_key(sheet_id).sheet1
        
        existing_invoices = set(worksheet.col_values(3)[1:])
        unique_sales = [s for s in sales_data if s['invoice'] not in existing_invoices]
        
        if not unique_sales:
            print("No new unique sales to add (all were duplicates).")
            return
            
        print(f"Preparing {len(unique_sales)} unique rows for upload...")
        rows_to_append = []
        if not worksheet.get_all_values(): # Add headers if sheet is empty
            rows_to_append.append(["Timestamp", "Name", "Invoice ID", "Amount"])

        for sale in unique_sales:
            rows_to_append.append([
                datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                sale["name"], sale["invoice"], sale["amount"]
            ])

        worksheet.append_rows(rows_to_append, value_input_option='USER_ENTERED')
        print(f"🎉 SUCCESS: Appended {len(unique_sales)} new rows to the sheet!")
    except Exception as e:
        print(f"❌ Failed to update spreadsheet: {e}")

def main():
    """Main function to run the scraper."""
    print("\n======== Starting Stealth Scraper v3 ========")
    load_dotenv()
    sheet_id = os.getenv("GOOGLE_SHEET_ID")
    
    if not sheet_id:
        print("Error: GOOGLE_SHEET_ID not found.")
        return

    gc = authenticate_google()
    if not gc: return

    driver = setup_driver()
    if not driver: return
    
    try:
        sales_data = extract_sales_data(driver)
        update_spreadsheet(gc, sheet_id, sales_data)
    finally:
        if driver:
            driver.quit()
        print("\n======== Script Finished ========")

if __name__ == "__main__":
    main()

