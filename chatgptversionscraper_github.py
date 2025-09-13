import os
import re
import time
import platform
import datetime
import json # --- ADDED --- For the new upload function
import requests # --- ADDED --- For the new upload function
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service # --- ADDED --- For GitHub Actions driver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from dotenv import load_dotenv

import gspread
# --- REMOVED --- No longer need browser-based auth libraries
# from google.oauth2.credentials import Credentials
# from google_auth_oauthlib.flow import InstalledAppFlow
# from pydrive.auth import GoogleAuth
# from pydrive.drive import GoogleDrive

# Load environment variables
load_dotenv()

# === Google Sheets + Drive Setup ===
# --- CHANGED --- SCOPES are now defined within gspread and the new upload function
CREDENTIALS_FILE = "credentials.json"  # Service Account credentials file
SPREADSHEET_ID = os.getenv("GOOGLE_SHEET_ID")
DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID")

# --- REPLACED --- Simplified authentication using the service account JSON file.
# This single line replaces all the old complex code with `InstalledAppFlow` and `token.json`.
print("Authenticating with Google Service Account...")
gc = gspread.service_account(filename=CREDENTIALS_FILE)
print("Authentication successful.")


# === Selenium Setup ===
# --- REPLACED --- This function now detects if it's running in GitHub Actions
def create_driver():
    """Creates a Chrome driver with the correct options for local or GitHub Actions."""
    chrome_options = Options()
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    # Check if running in the GitHub Actions environment
    if os.getenv('GITHUB_ACTIONS') == 'true':
        print("Running in GitHub Actions environment. Using headless mode.")
        chrome_options.add_argument("--headless=new")
        # These paths are specific to the GitHub Actions runner environment
        chrome_options.binary_location = "/usr/bin/chromium-browser"
        service = Service("/usr/bin/chromedriver")
        driver = webdriver.Chrome(service=service, options=chrome_options)
    else:
        print("Running in local environment.")
        # Optional: uncomment the next line to run headless on your local machine too
        # chrome_options.add_argument("--headless=new")
        driver = webdriver.Chrome(options=chrome_options)
    
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver


# --- REPLACED --- PyDrive is removed. This new function uses the gspread credentials
# to upload files directly, which is simpler and more reliable in an automated environment.
def upload_screenshot(file_path):
    """Uploads a file to Google Drive using the authenticated gspread session."""
    print(f"Uploading {file_path} to Google Drive...")
    
    # Use the authenticated session from gspread's client
    session = gc.ssession
    
    # 1. Get an upload URL
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
    if 'Location' not in r.headers:
        print("Error: Could not get upload URL from Google Drive.")
        print("Response:", r.text)
        return None
    upload_url = r.headers['Location']

    # 2. Upload the file content
    with open(file_path, 'rb') as f:
        file_data = f.read()
    
    upload_headers = {'Content-Type': 'image/png'} # Or the correct mime type
    r_upload = session.put(upload_url, headers=upload_headers, data=file_data)
    
    if r_upload.status_code == 200:
        file_id = r_upload.json()['id']
        print(f"File uploaded successfully. File ID: {file_id}")
        
        # 3. Make the file public (anyone with the link can view)
        permission_url = f'https://www.googleapis.com/drive/v3/files/{file_id}/permissions'
        permission_data = {'type': 'anyone', 'role': 'reader'}
        r_perm = session.post(permission_url, headers=headers, data=json.dumps(permission_data))
        
        if r_perm.status_code == 200:
            print("File permission set to public.")
            return f"https://drive.google.com/file/d/{file_id}/view?usp=drivesdk"
        else:
            print("Warning: Could not set file permission to public.")
            return f"https://drive.google.com/file/d/{file_id}/" # Return non-public link
    else:
        print("Error: File upload failed.")
        print("Response:", r_upload.text)
        return None


def scrape_sales():
    # --- CHANGED --- Now uses the new create_driver function
    driver = create_driver()
    driver.get("https://std.nest.net.np")
    
    # ... (the rest of your scrape_sales function does not need to be changed) ...
    # ... (it is very long, so I am omitting it for clarity, but you should keep it as is) ...

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    print(f"Page title: {driver.title}")
    
    # Wait for content to load - this looks like a React app that needs time to render
    wait = WebDriverWait(driver, 30)
    
    print("Waiting for page content to load...")
    time.sleep(5)  # Give some time for initial load
    
    # Check if page is still showing "Loading..."
    for attempt in range(5):
        page_text = driver.find_element(By.TAG_NAME, "body").text
        print(f"Attempt {attempt + 1}: Page content: {page_text[:100]}...")
        
        if "Loading..." not in page_text:
            print("Content has loaded!")
            break
        else:
            print("Still loading, waiting 3 more seconds...")
            time.sleep(3)
    
    # Look for any content
    leaders = []
    try:
        # First try the proven working selectors from the old script
        print("Trying proven working selectors...")
        container = driver.find_elements(By.CSS_SELECTOR, "div.space-y-4")
        if container:
            print(f"Found container with div.space-y-4")
            leaders = container[0].find_elements(By.CSS_SELECTOR, "div.p-4.transition")
            print(f"Found {len(leaders)} entries with div.p-4.transition")
        
        # If that didn't work, try the newer approach
        if len(leaders) == 0:
            print("Trying newer selectors...")
            # Look for MuiPaper-root elements
            leaders = driver.find_elements(By.CSS_SELECTOR, "div.MuiPaper-root")
            print(f"Found {len(leaders)} MuiPaper-root elements")
            
            if len(leaders) == 0:
                # Try alternative selectors for any card-like elements
                alternatives = [
                    "div[class*='Paper']",
                    "div[class*='card']", 
                    "div[class*='Card']",
                    "div[class*='leader']",
                    "div[class*='Leader']",
                    ".leaderboard",
                    "[class*='leaderboard']",
                    "[class*='Leaderboard']",
                    "div[class*='item']",
                    "div[class*='entry']",
                    "div[role='button']",
                    "div[class*='clickable']"
                ]
                
                for selector in alternatives:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    print(f"Found {len(elements)} elements with selector: {selector}")
                    if elements:
                        leaders = elements
                        break
                
                # If still no elements found, let's see what's actually on the page
                if len(leaders) == 0:
                    all_divs = driver.find_elements(By.TAG_NAME, "div")
                    print(f"Total divs on page: {len(all_divs)}")
                    
                    # Look for any divs with meaningful text content
                    content_divs = []
                    for div in all_divs[:20]:  # Check first 20 divs
                        text = div.text.strip()
                        if len(text) > 10 and "Loading" not in text:
                            content_divs.append(div)
                            print(f"Content div found: {text[:50]}...")
                    
                    if content_divs:
                        leaders = content_divs
    
    except Exception as e:
        print(f"Error finding page elements: {e}")
        
    all_rows = []
    screenshot_link = ""  # Will be set after expanding all entries
    
    print(f"\n=== Processing {len(leaders)} leader elements ===")

    # Process the leaders we found
    # First check if we have the proven working structure
    using_proven_selectors = len([leader for leader in leaders if "span.font-semibold" in str(leader.get_attribute("innerHTML"))]) > 0
    
    if using_proven_selectors:
        print("Using proven selector extraction method")
        leader_cards = leaders  # Use all elements found
    else:
        print("Using newer selector extraction method") 
        # Skip the header (first element)
        leader_cards = [leader for leader in leaders if "#" in leader.text and "Leaderboard" not in leader.text]
    
    print(f"Found {len(leader_cards)} actual leader cards to process")
    
    for i, leader in enumerate(leader_cards):
        try:
            text = leader.text.strip()
            print(f"\n=== Processing Leader {i+1} ===")
            print(f"Initial text: {text[:150]}...")
            
            # Extract name - try different approaches
            name_text = "Unknown"
            
            if using_proven_selectors:
                # Try to find name using span.font-semibold
                try:
                    name_elem = leader.find_element(By.CSS_SELECTOR, "span.font-semibold")
                    name_text = name_elem.text.strip()
                    print(f"Extracted name using span.font-semibold: '{name_text}'")
                except:
                    print("Could not find span.font-semibold, trying text parsing...")
            
            if name_text == "Unknown":
                # Extract name from text like "#1 Subas Kandel"
                name_match = re.search(r"#\d+\s+([^\n🧾💵]+)", text)
                name_text = name_match.group(1).strip() if name_match else "Unknown"
                print(f"Extracted name using regex: '{name_text}'")
            
            # Skip if name is Unknown or empty
            if name_text == "Unknown" or not name_text:
                print("Skipping - no valid name found")
                continue
                
            # Try clicking to expand and get detailed sales info
            detailed_sales_found = False
            try:
                print("Attempting to click and expand...")
                # Scroll into view first
                driver.execute_script("arguments[0].scrollIntoView(true);", leader)
                time.sleep(1)
                
                # Click to expand
                leader.click()
                time.sleep(3)  # Wait longer for expansion
                
                # Get updated text after clicking
                expanded_text = leader.text.strip()
                print(f"Expanded text length: {len(expanded_text)} vs original: {len(text)}")
                
                if len(expanded_text) > len(text):
                    print(f"Successfully expanded! New text: {expanded_text[:300]}...")
                    text = expanded_text
                    
                    # Look for individual sales with invoice IDs
                    # Try multiple patterns for sales data
                    sales_patterns = [
                        r"Sale of Rs\.?\s*([\d,]+\.?\d*).*?Invoice ID:\s*#?(\d+)",
                        r"Rs\.?\s*([\d,]+\.?\d*).*?#(\d+)",
                        r"Amount:\s*Rs\.?\s*([\d,]+\.?\d*).*?Invoice.*?#?(\d+)",
                        r"([\d,]+\.?\d*).*?Invoice.*?#?(\d{8,})"
                    ]
                    
                    for pattern in sales_patterns:
                        sales_matches = re.findall(pattern, text, re.DOTALL | re.IGNORECASE)
                        if sales_matches:
                            print(f"Found {len(sales_matches)} sales using pattern: {pattern}")
                            detailed_sales_found = True
                            
                            for amount, invoice_id in sales_matches:
                                # Clean up amount (remove commas)
                                clean_amount = amount.replace(',', '')
                                
                                row = [
                                    datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                    name_text,
                                    invoice_id,
                                    clean_amount,
                                    "",  # Screenshot link will be added later
                                ]
                                all_rows.append(row)
                                print(f"✅ Added detailed sale: {name_text}, Invoice #{invoice_id}, Amount: Rs. {clean_amount}")
                            break
                    
                    # If no detailed sales found, try to find them in the DOM
                    if not detailed_sales_found:
                        print("Looking for sales in DOM elements...")
                        try:
                            # Look for child elements that might contain sales details
                            sales_elements = leader.find_elements(By.XPATH, ".//*[contains(text(), 'Sale') or contains(text(), 'Invoice') or contains(text(), 'Rs')]")
                            print(f"Found {len(sales_elements)} potential sales elements")
                            
                            for elem in sales_elements:
                                elem_text = elem.text.strip()
                                if len(elem_text) > 10:
                                    print(f"Sales element text: {elem_text}")
                                    
                                    # Try to extract from this element
                                    for pattern in sales_patterns:
                                        matches = re.findall(pattern, elem_text, re.DOTALL | re.IGNORECASE)
                                        if matches:
                                            detailed_sales_found = True
                                            for amount, invoice_id in matches:
                                                clean_amount = amount.replace(',', '')
                                                row = [
                                                    datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                                    name_text,
                                                    invoice_id,
                                                    clean_amount,
                                                    "",  # Screenshot link will be added later
                                                ]
                                                all_rows.append(row)
                                                print(f"✅ Added from DOM: {name_text}, Invoice #{invoice_id}, Amount: Rs. {clean_amount}")
                                            break
                        except Exception as dom_error:
                            print(f"Error searching DOM: {dom_error}")
                            
                else:
                    print("Element did not expand or same content")
                    
            except Exception as click_error:
                print(f"Could not click/expand element: {click_error}")
            
            # If no detailed sales found, fall back to summary
            if not detailed_sales_found:
                print("No detailed sales found, trying summary extraction...")
                # Pattern like "🧾 1 sales | 💵 Rs. 12692.07"
                summary_patterns = [
                    r"🧾\s*(\d+)\s*sales?\s*\|\s*💵\s*Rs\.?\s*([\d,]+\.?\d*)",
                    r"(\d+)\s*sales?.*?Rs\.?\s*([\d,]+\.?\d*)",
                    r"sales:\s*(\d+).*?Rs\.?\s*([\d,]+\.?\d*)"
                ]
                
                for pattern in summary_patterns:
                    summary_match = re.search(pattern, text, re.IGNORECASE)
                    if summary_match:
                        sales_count, total_amount = summary_match.groups()
                        clean_amount = total_amount.replace(',', '')
                        print(f"Found summary: {sales_count} sales, total Rs. {clean_amount}")
                        
                        # Generate a meaningful invoice ID for summary
                        summary_id = f"SUMMARY_{int(time.time())}"
                        
                        row = [
                            datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            name_text,
                            summary_id,
                            clean_amount,
                            "",  # Screenshot link will be added later
                        ]
                        all_rows.append(row)
                        print(f"✅ Added summary: {name_text}, ID: {summary_id}, Amount: Rs. {clean_amount}")
                        break

        except Exception as e:
            print(f"Error parsing leader {i+1}: {e}")
            import traceback
            traceback.print_exc()

    # Take final screenshot after expanding all entries (one per day)
    today_date = datetime.datetime.now().strftime("%Y-%m-%d")
    daily_screenshot_path = os.path.join(os.getcwd(), f"daily_sales_screenshot_{today_date}.png")
    screenshot_link_file = os.path.join(os.getcwd(), f"screenshot_link_{today_date}.txt")
    
    # Check if today's screenshot and link already exist
    if os.path.exists(daily_screenshot_path) and os.path.exists(screenshot_link_file):
        print(f"\n📸 Using existing screenshot and link for today: {daily_screenshot_path}")
        # Read the existing screenshot link
        with open(screenshot_link_file, 'r') as f:
            screenshot_link = f.read().strip()
        print(f"Using existing screenshot link: {screenshot_link}")
    else:
        print(f"\n📸 Taking new daily screenshot for {today_date} with all entries expanded...")
        driver.save_screenshot(daily_screenshot_path)
        print(f"Screenshot saved: {daily_screenshot_path}")
        
        # Upload screenshot to Drive
        screenshot_link = upload_screenshot(daily_screenshot_path)
        print(f"Screenshot uploaded: {screenshot_link}")
        
        # Save the screenshot link for reuse
        if screenshot_link:
            with open(screenshot_link_file, 'w') as f:
                f.write(screenshot_link)
            print(f"Screenshot link saved for daily reuse")
    
    # Update all rows with the screenshot link
    # Only add screenshot link to the first row if we have multiple rows (for merging)
    if len(all_rows) > 1:
        # Only first row gets the screenshot link, others stay empty for cleaner merging
        all_rows[0][4] = screenshot_link
        for i in range(1, len(all_rows)):
            all_rows[i][4] = ""  # Keep empty for merged cells
    else:
        # Single row gets the screenshot link
        for row in all_rows:
            row[4] = screenshot_link

    driver.quit()
    return all_rows

# ... (The rest of your functions: setup_worksheet_headers, check_for_duplicates, etc. are all perfectly fine) ...
# ... (Keep them exactly as they are) ...

def setup_worksheet_headers(worksheet):
    """Ensure the worksheet has proper headers"""
    try:
        # Check if headers exist
        headers = worksheet.row_values(1)
        expected_headers = ["Timestamp", "Name", "Invoice ID", "Amount", "Screenshot Link"]
        
        if not headers or headers != expected_headers:
            print("Setting up worksheet headers...")
            worksheet.clear()
            worksheet.append_row(expected_headers)
            print("Headers added to worksheet")
        else:
            print("Headers already exist")
    except Exception as e:
        print(f"Error setting up headers: {e}")
        # If there's an error, just add headers anyway
        worksheet.clear()
        worksheet.append_row(["Timestamp", "Name", "Invoice ID", "Amount", "Screenshot Link"])

def check_for_duplicates(worksheet, new_rows):
    """Check for duplicate entries and filter them out"""
    try:
        # Get existing data
        existing_data = worksheet.get_all_values()[1:]  # Skip header row
        existing_invoices = set(row[2] for row in existing_data if len(row) > 2)  # Invoice ID column
        
        # Filter out duplicates
        unique_rows = []
        duplicates_found = 0
        
        for row in new_rows:
            invoice_id = row[2]
            if invoice_id not in existing_invoices:
                unique_rows.append(row)
                existing_invoices.add(invoice_id)  # Add to set to avoid duplicates within this batch
            else:
                duplicates_found += 1
                print(f"⚠ Skipping duplicate: {row[1]} - Invoice #{invoice_id}")
        
        print(f"Filtered out {duplicates_found} duplicates")
        return unique_rows
        
    except Exception as e:
        print(f"Error checking duplicates: {e}")
        return new_rows  # Return original rows if error

def merge_screenshot_cells(worksheet, start_row, end_row):
    """Merge screenshot cells for multiple sales from the same day"""
    try:
        if start_row < end_row:  # Only merge if there are multiple rows
            # Use the Google Sheets API to merge cells in column E (Screenshot Link column)
            spreadsheet_id = worksheet.spreadsheet.id
            sheet_id = worksheet.id
            
            merge_request = {
                "requests": [
                    {
                        "mergeCells": {
                            "range": {
                                "sheetId": sheet_id,
                                "startRowIndex": start_row - 1,  # 0-indexed
                                "endRowIndex": end_row,  # exclusive
                                "startColumnIndex": 4,  # Column E (0-indexed)
                                "endColumnIndex": 5  # exclusive
                            },
                            "mergeType": "MERGE_ALL"
                        }
                    }
                ]
            }
            
            # Execute the merge request
            worksheet.spreadsheet.batch_update(merge_request)
            print(f"🔗 Merged screenshot cells: E{start_row}:E{end_row}")
    except Exception as e:
        print(f"Error merging cells: {e}")

def should_add_date_separator(worksheet, new_date):
    """Check if we need to add a blank row for date separation"""
    try:
        current_data = worksheet.get_all_values()
        if len(current_data) > 1:  # Has data beyond headers
            # Get the last non-empty row's date
            for row in reversed(current_data[1:]):  # Skip header
                if row and row[0]:  # Check if row has timestamp
                    last_timestamp = row[0]
                    # Extract date from timestamp (format: YYYY-MM-DD HH:MM:SS)
                    last_date = last_timestamp.split(' ')[0] if ' ' in last_timestamp else last_timestamp[:10]
                    # Compare dates
                    if last_date != new_date:
                        return True
                    break
        return False
    except Exception as e:
        print(f"Error checking date separator: {e}")
        return False

def main():
    print("🚀 Starting sales scraper...")
    
    rows = scrape_sales()
    if not rows:
        print("⚠ No sales found.")
        return

    print(f"\n📊 Processing {len(rows)} extracted sales...")
    
    # Open spreadsheet
    sh = gc.open_by_key(SPREADSHEET_ID)
    worksheet = sh.sheet1
    
    # Setup headers
    setup_worksheet_headers(worksheet)
    
    # Check for duplicates
    unique_rows = check_for_duplicates(worksheet, rows)
    
    if unique_rows:
        # Get current date from the first row
        current_date = datetime.datetime.now().strftime("%Y-%m-%d")
        
        # Check if we need to add a date separator (blank row)
        if should_add_date_separator(worksheet, current_date):
            # Add a blank row before new data
            worksheet.append_row(["", "", "", "", ""])
            print("📅 Added blank row for new date separation")
        
        # Get the current row count to know where new data starts
        current_data = worksheet.get_all_values()
        start_row = len(current_data) + 1  # +1 because rows are 1-indexed
        
        # Add new rows
        worksheet.append_rows(unique_rows)
        print(f"✅ Successfully added {len(unique_rows)} new sales to spreadsheet!")
        
        # Merge screenshot cells if multiple rows were added
        if len(unique_rows) > 1:
            end_row = start_row + len(unique_rows) - 1
            merge_screenshot_cells(worksheet, start_row, end_row)
        
        # Print summary
        print("\n📈 Summary of added sales:")
        for row in unique_rows:
            print(f"  • {row[1]}: Invoice #{row[2]}, Rs. {row[3]}")
    else:
        print("ℹ No new sales to add (all were duplicates)")


if __name__ == "__main__":
    main()
