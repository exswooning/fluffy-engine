import os
import re
import time
import platform
import datetime
import json 
import requests 
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service 
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from dotenv import load_dotenv
import gspread

# Load environment variables
load_dotenv()

# === Google Sheets + Drive Setup ===
CREDENTIALS_FILE = "credentials.json"
SPREADSHEET_ID = os.getenv("GOOGLE_SHEET_ID")
DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID")

# --- Simplified authentication using the service account JSON file ---
print("Authenticating with Google Service Account...")
gc = gspread.service_account(filename=CREDENTIALS_FILE)
print("Authentication successful.")


# === Selenium Setup ===
def create_driver():
    """Creates a Chrome driver with the correct options for local or GitHub Actions."""
    chrome_options = Options()
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    if os.getenv('GITHUB_ACTIONS') == 'true':
        print("Running in GitHub Actions environment. Using headless mode.")
        chrome_options.add_argument("--headless=new")
        chrome_options.binary_location = "/usr/bin/chromium-browser"
        service = Service("/usr/bin/chromedriver")
        driver = webdriver.Chrome(service=service, options=chrome_options)
    else:
        print("Running in local environment.")
        driver = webdriver.Chrome(options=chrome_options)
    
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver


def upload_screenshot(file_path):
    """Uploads a file to Google Drive using the authenticated gspread session."""
    print(f"Uploading {file_path} to Google Drive...")
    
    try:
        # --- FINAL FIX --- Changed to the correct gc.session
        session = gc.session
        
        # 1. Get an upload URL
        print("Step 1: Requesting upload URL...")
        metadata = {
            'name': os.path.basename(file_path),
            'parents': [DRIVE_FOLDER_ID]
        }
        files_url = 'https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable'
        headers = {
            'Authorization': 'Bearer ' + session.credentials.access_token,
            'Content-Type': 'application/json'
        }
        r = session.post(files_url, headers=headers, data=json.dumps(metadata))
        r.raise_for_status()
        
        if 'Location' not in r.headers:
            print("Error: Could not get upload URL from Google Drive.")
            print("Response:", r.text)
            return None
        upload_url = r.headers['Location']
        print("Step 1 successful. Got upload URL.")

        # 2. Upload the file content
        print("Step 2: Uploading file content...")
        with open(file_path, 'rb') as f:
            file_data = f.read()
        
        upload_headers = {'Content-Type': 'image/png'}
        r_upload = session.put(upload_url, headers=upload_headers, data=file_data)
        r_upload.raise_for_status()
        
        response_json = r_upload.json()
        file_id = response_json['id']
        print(f"Step 2 successful. File uploaded. File ID: {file_id}")
        
        # 3. Make the file public
        print("Step 3: Setting file permissions...")
        permission_url = f'https://www.googleapis.com/drive/v3/files/{file_id}/permissions'
        permission_data = {'type': 'anyone', 'role': 'reader'}
        r_perm = session.post(permission_url, headers=headers, data=json.dumps(permission_data))
        r_perm.raise_for_status()
        
        print("Step 3 successful. File permission set to public.")
        return f"https://drive.google.com/file/d/{file_id}/view?usp=drivesdk"

    except Exception as e:
        print(f"An unexpected error occurred in upload_screenshot: {e}")
        import traceback
        traceback.print_exc()
        return None


def scrape_sales():
    driver = create_driver()
    driver.get("https://std.nest.net.np")
    
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    print(f"Page title: {driver.title}")
    
    print("Waiting for page content to load...")
    time.sleep(5)
    
    for attempt in range(5):
        page_text = driver.find_element(By.TAG_NAME, "body").text
        print(f"Attempt {attempt + 1}: Page content: {page_text[:100]}...")
        if "Loading..." not in page_text:
            print("Content has loaded!")
            break
        else:
            print("Still loading, waiting 3 more seconds...")
            time.sleep(3)
    
    leaders = []
    try:
        print("Trying to find leader elements...")
        # Simplified the selector logic based on previous logs
        leaders = driver.find_elements(By.CSS_SELECTOR, "div.p-4.transition")
        if not leaders:
             leaders = driver.find_elements(By.CSS_SELECTOR, "div.MuiPaper-root")
        if not leaders:
            leaders = driver.find_elements(By.CSS_SELECTOR, "div[class*='item']")
        print(f"Found {len(leaders)} potential leader elements.")

    except Exception as e:
        print(f"Error finding page elements: {e}")
        
    all_rows = []
    screenshot_link = ""
    
    print(f"\n=== Processing {len(leaders)} leader elements ===")
    
    leader_cards = [leader for leader in leaders if "#" in leader.text and "Leaderboard" not in leader.text]
    if not leader_cards and leaders: # Fallback if primary filter fails
        leader_cards = leaders

    print(f"Found {len(leader_cards)} actual leader cards to process")
    
    for i, leader in enumerate(leader_cards):
        try:
            text = leader.text.strip()
            print(f"\n=== Processing Leader {i+1} ===")
            print(f"Initial text: {text[:150]}...")
            
            name_match = re.search(r"#\d+\s+([^\n🧾💵]+)", text)
            name_text = name_match.group(1).strip() if name_match else "Unknown"
            print(f"Extracted name: '{name_text}'")
            
            if name_text == "Unknown" or not name_text:
                print("Skipping - no valid name found")
                continue
                
            detailed_sales_found = False
            try:
                print("Attempting to click and expand...")
                driver.execute_script("arguments[0].scrollIntoView(true);", leader)
                time.sleep(1)
                leader.click()
                time.sleep(3)
                
                expanded_text = leader.text.strip()
                if len(expanded_text) > len(text):
                    print(f"Successfully expanded! New text: {expanded_text[:300]}...")
                    text = expanded_text
                    
                    sales_patterns = [
                        r"Sale of Rs\.?\s*([\d,]+\.?\d*).*?Invoice ID:\s*#?(\d+)",
                        r"Rs\.?\s*([\d,]+\.?\d*).*?#(\d+)"
                    ]
                    
                    for pattern in sales_patterns:
                        sales_matches = re.findall(pattern, text, re.DOTALL | re.IGNORECASE)
                        if sales_matches:
                            detailed_sales_found = True
                            for amount, invoice_id in sales_matches:
                                clean_amount = amount.replace(',', '')
                                row = [
                                    datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                    name_text, invoice_id, clean_amount, ""
                                ]
                                all_rows.append(row)
                                print(f"✅ Added detailed sale: {name_text}, Invoice #{invoice_id}, Amount: Rs. {clean_amount}")
                            break
            except Exception as click_error:
                print(f"Could not click/expand element: {click_error}")
            
            if not detailed_sales_found:
                print("No detailed sales found, trying summary extraction...")
                summary_match = re.search(r"🧾\s*(\d+)\s*sales?\s*\|\s*💵\s*Rs\.?\s*([\d,]+\.?\d*)", text, re.IGNORECASE)
                if summary_match:
                    sales_count, total_amount = summary_match.groups()
                    clean_amount = total_amount.replace(',', '')
                    summary_id = f"SUMMARY_{int(time.time())}"
                    row = [
                        datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        name_text, summary_id, clean_amount, ""
                    ]
                    all_rows.append(row)
                    print(f"✅ Added summary: {name_text}, ID: {summary_id}, Amount: Rs. {clean_amount}")

        except Exception as e:
            print(f"Error parsing leader {i+1}: {e}")
            import traceback
            traceback.print_exc()

    today_date = datetime.datetime.now().strftime("%Y-%m-%d")
    daily_screenshot_path = os.path.join(os.getcwd(), f"daily_sales_screenshot_{today_date}.png")
    screenshot_link_file = os.path.join(os.getcwd(), f"screenshot_link_{today_date}.txt")
    
    if os.path.exists(daily_screenshot_path) and os.path.exists(screenshot_link_file):
        print(f"\n📸 Using existing screenshot and link for today.")
        with open(screenshot_link_file, 'r') as f:
            screenshot_link = f.read().strip()
    else:
        print(f"\n📸 Taking new daily screenshot...")
        driver.save_screenshot(daily_screenshot_path)
        screenshot_link = upload_screenshot(daily_screenshot_path)
        print(f"Screenshot uploaded: {screenshot_link}")
        if screenshot_link:
            with open(screenshot_link_file, 'w') as f:
                f.write(screenshot_link)
    
    for row in all_rows:
        row[4] = screenshot_link

    driver.quit()
    return all_rows, screenshot_link

def setup_worksheet_headers(worksheet):
    try:
        headers = worksheet.row_values(1)
        expected_headers = ["Timestamp", "Name", "Invoice ID", "Amount", "Screenshot Link"]
        if not headers or headers != expected_headers:
            worksheet.clear()
            worksheet.append_row(expected_headers)
            print("Headers added to worksheet")
    except Exception as e:
        print(f"Error setting up headers: {e}")

def check_for_duplicates(worksheet, new_rows):
    try:
        existing_data = worksheet.get_all_values()[1:]
        existing_invoices = set(row[2] for row in existing_data if len(row) > 2)
        unique_rows = []
        for row in new_rows:
            if row[2] not in existing_invoices:
                unique_rows.append(row)
                existing_invoices.add(row[2])
            else:
                print(f"⚠ Skipping duplicate: Invoice #{row[2]}")
        return unique_rows
    except Exception as e:
        print(f"Error checking duplicates: {e}")
        return new_rows

def merge_screenshot_cells(worksheet, start_row, end_row):
    try:
        if start_row < end_row:
            merge_request = {
                "requests": [{"mergeCells": {
                    "range": {
                        "sheetId": worksheet.id, "startRowIndex": start_row - 1,
                        "endRowIndex": end_row, "startColumnIndex": 4, "endColumnIndex": 5
                    }, "mergeType": "MERGE_ALL"
                }}]
            }
            worksheet.spreadsheet.batch_update(merge_request)
            print(f"🔗 Merged screenshot cells: E{start_row}:E{end_row}")
    except Exception as e:
        print(f"Error merging cells: {e}")

def should_add_date_separator(worksheet, new_date):
    try:
        last_row = worksheet.get_all_values()[-1]
        if last_row and last_row[0]:
            last_date = last_row[0].split(' ')[0]
            return last_date != new_date
        return False
    except (IndexError, gspread.exceptions.APIError):
        return False # Cannot determine last date, so don't add separator

def main():
    print("🚀 Starting sales scraper...")
    rows, screenshot_link = scrape_sales()
    
    if not rows:
        print("⚠ No sales found.")
        now_utc = datetime.datetime.utcnow()
        if now_utc.hour == 11 and 55 <= now_utc.minute <= 59:
            print("This is the 11:55 UTC run. Preparing 'No Sales' entry.")
            today_date_str = datetime.datetime.now().strftime("%Y-%m-%d")
            rows = [[
                datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "No Sales Recorded", f"NO_SALES_{today_date_str}", "", screenshot_link
            ]]
        else:
            print("Not the 11:55 UTC run, no update will be made.")
            return

    if not rows: return

    print(f"\n📊 Processing {len(rows)} entries...")
    worksheet = gc.open_by_key(SPREADSHEET_ID).sheet1
    setup_worksheet_headers(worksheet)
    unique_rows = check_for_duplicates(worksheet, rows)
    
    if unique_rows:
        current_date = datetime.datetime.now().strftime("%Y-%m-%d")
        if should_add_date_separator(worksheet, current_date):
            worksheet.append_row(["", "", "", "", ""])
            print("📅 Added blank row for new date separation")
        
        start_row = len(worksheet.get_all_values()) + 1
        worksheet.append_rows(unique_rows)
        
        if unique_rows[0][1] == "No Sales Recorded":
            print("✅ Successfully added 'No Sales Recorded' to spreadsheet!")
        else:
            print(f"✅ Successfully added {len(unique_rows)} new sales to spreadsheet!")

        if len(unique_rows) > 1:
            merge_screenshot_cells(worksheet, start_row, start_row + len(unique_rows) - 1)
        
        print("\n📈 Summary of added entries:")
        for row in unique_rows:
            print(f"  • {row[1]}: Invoice #{row[2]}, Rs. {row[3]}" if row[1] != "No Sales Recorded" else f"  • {row[1]}")
    else:
        print("ℹ No new entries to add (all were duplicates).")

if __name__ == "__main__":
    main()

