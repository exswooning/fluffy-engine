import os
import tempfile
import datetime
import time
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.common.action_chains import ActionChains
from webdriver_manager.chrome import ChromeDriverManager
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
import gspread
import re

# --- Configuration ---
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
WEBSITE_URL = "http://std.nest.net.np/"
CREDENTIALS_FILE = "credentials.json"

# --- Helper Functions ---

def load_environment_variables():
    """Loads environment variables from the .env file."""
    load_dotenv()
    sheet_id = os.getenv("GOOGLE_SHEET_ID")
    drive_folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID")

    if not sheet_id:
        print("Error: Missing GOOGLE_SHEET_ID in .env file.")
        return None, None
    return sheet_id, drive_folder_id

def authenticate_google_service_account():
    """Authenticates using a service account credentials file."""
    try:
        if not os.path.exists(CREDENTIALS_FILE):
            print(f"Error: Credentials file not found at '{CREDENTIALS_FILE}'")
            return None, None
            
        creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
        gc = gspread.authorize(creds)
        drive_service = build('drive', 'v3', credentials=creds)
        
        print("✓ Google Service Account authentication successful.")
        return gc, drive_service
    except Exception as e:
        print(f"An error occurred during Google authentication: {e}")
        return None, None

def setup_driver():
    """Sets up and returns a Selenium Chrome WebDriver instance for a server environment."""
    print("Setting up browser driver for headless environment...")
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1200")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    try:
        service = ChromeService(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return driver
    except Exception as e:
        print(f"Error setting up WebDriver: {e}")
        return None

def extract_sales_data(driver):
    """Controls the scraping process with a robust click-and-verify loop."""
    all_sales_data = []
    wait = WebDriverWait(driver, 15)
    
    leaderboard_entries = driver.find_elements(By.CSS_SELECTOR, "div.p-4.transition")
    num_entries = len(leaderboard_entries)
    print(f"Found {num_entries} leaderboard entries.")

    for i in range(num_entries):
        try:
            # Re-find elements each time to prevent stale references
            current_entries = driver.find_elements(By.CSS_SELECTOR, "div.p-4.transition")
            entry_element = current_entries[i]
            
            entry_name = f"Entry {i+1}"
            try:
                name_element = entry_element.find_element(By.CSS_SELECTOR, "span.font-semibold")
                entry_name = name_element.text.strip()
            except NoSuchElementException:
                print(f"Could not find name for entry {i+1}.")

            print(f"\n--- Processing: {entry_name} ---")

            initial_text_length = len(entry_element.text)
            
            print("  Attempting human-like click to expand...")
            ActionChains(driver).move_to_element(entry_element).click().perform()
            
            # Wait for the content to change by checking for an increase in text length
            wait.until(
                lambda d: len(d.find_elements(By.CSS_SELECTOR, "div.p-4.transition")[i].text) > initial_text_length
            )
            print("  ✓ Expansion confirmed by content change.")

            expanded_entry_element = driver.find_elements(By.CSS_SELECTOR, "div.p-4.transition")[i]
            full_text = expanded_entry_element.text
            
            sales_pattern = r"Sale of Rs\.?\s*([\d,]+\.?\d*).*?Invoice ID:\s*#?(\d+)"
            matches = re.findall(sales_pattern, full_text, re.IGNORECASE)
            
            if not matches:
                print(f"  ⚠️ No detailed sales found for {entry_name} after expansion.")
                continue

            for amount, invoice_id in matches:
                clean_amount = amount.replace(',', '')
                sale_record = {'name': entry_name, 'amount': clean_amount, 'invoice': invoice_id}
                all_sales_data.append(sale_record)
                print(f"    ✓ Extracted Sale: Amount=Rs.{clean_amount}, Invoice=#{invoice_id}")
        
        except TimeoutException:
            print(f"  ❌ Timed out waiting for {entry_name} to expand. The site may be slow or the click failed. Skipping.")
        except Exception as e:
            print(f"  ❌ An error occurred processing {entry_name}: {e}")
            
    return all_sales_data

def upload_to_drive(drive_service, file_path, folder_id):
    """Uploads a file to a specific Google Drive folder."""
    if not folder_id:
        print("Google Drive Folder ID not provided, skipping upload.")
        return "Upload Skipped"
    try:
        file_metadata = {'name': os.path.basename(file_path), 'parents': [folder_id]}
        media = MediaFileUpload(file_path, mimetype='image/png')
        file = drive_service.files().create(body=file_metadata, media_body=media, fields='webViewLink').execute()
        link = file.get('webViewLink')
        print(f"✓ Screenshot uploaded successfully: {link}")
        return link
    except HttpError as error:
        print(f"An error occurred during file upload: {error}")
        return "Upload Failed"

def check_for_duplicates(worksheet, sales_records):
    """Filters out sales records that already exist in the sheet."""
    print("Checking for duplicate entries...")
    try:
        existing_data = worksheet.get_all_values()
        existing_invoices = set(row[2] for row in existing_data[1:]) # Skip header
        
        unique_records = [r for r in sales_records if r['invoice'] not in existing_invoices]
        
        print(f"Found {len(unique_records)} new unique sales to add.")
        return unique_records
    except Exception as e:
        print(f"Could not check for duplicates due to an error: {e}. Appending all data.")
        return sales_records

def main():
    """Main function to orchestrate the scraping and data upload process."""
    print("\n======== Starting Final Scraper ========")
    
    spreadsheet_id, drive_folder_id = load_environment_variables()
    if not spreadsheet_id: return
        
    gc, drive_service = authenticate_google_service_account()
    if not gc or not drive_service: return

    driver = setup_driver()
    if not driver: return

    try:
        print(f"Navigating to {WEBSITE_URL}...")
        driver.get(WEBSITE_URL)
        wait = WebDriverWait(driver, 20)
        
        print("Waiting for main sales container to load...")
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.space-y-4")))
        
        print("Main container found. Allowing page to render...")
        time.sleep(5)

        sales_data = extract_sales_data(driver)
        
        print(f"\n📊 FINAL RESULTS: Found {len(sales_data)} total sales records.")

        if not sales_data:
            print("No new data to upload.")
            return

        print("Opening Google Sheet...")
        worksheet = gc.open_by_key(spreadsheet_id).sheet1

        unique_sales_data = check_for_duplicates(worksheet, sales_data)

        if not unique_sales_data:
            print("No new unique data to upload (all entries were duplicates).")
            return

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        screenshot_filename = f"sales_screenshot_{timestamp}.png"
        temp_dir = tempfile.gettempdir()
        screenshot_path = os.path.join(temp_dir, screenshot_filename)

        print(f"Taking screenshot: {screenshot_path}")
        driver.save_screenshot(screenshot_path)
        
        screenshot_link = upload_to_drive(drive_service, screenshot_path, drive_folder_id)
        
        print("Preparing data for upload...")
        rows_to_append = []
        
        if not worksheet.get_all_values():
            rows_to_append.append(["Timestamp", "Name", "Invoice ID", "Amount", "Screenshot Link"])

        for sale in unique_sales_data:
            rows_to_append.append([
                datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                sale["name"], sale["invoice"], sale["amount"], screenshot_link
            ])

        print(f"Appending {len(rows_to_append)} unique rows to the sheet...")
        worksheet.append_rows(rows_to_append, value_input_option='USER_ENTERED')
        
        print("🎉 SUCCESS: Data uploaded to Google Sheet!")

    except Exception as e:
        print(f"A critical error occurred: {e}")
    finally:
        if driver:
            driver.quit()
        if 'screenshot_path' in locals() and os.path.exists(screenshot_path):
            os.remove(screenshot_path)
            print("Cleaned up temporary screenshot.")
            
        print("\n======== Script Finished ========")

if __name__ == "__main__":
    main()

