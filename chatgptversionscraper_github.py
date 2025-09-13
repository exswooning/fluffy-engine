import os
import re
import time
import platform
import datetime
import sys
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException
from dotenv import load_dotenv

try:
    import gspread
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from pydrive.auth import GoogleAuth
    from pydrive.drive import GoogleDrive
except ImportError as e:
    print(f"Missing required package: {e}")
    print("Please install required packages using: pip install -r requirements.txt")
    sys.exit(1)

# Load environment variables
load_dotenv()

# === Google Sheets + Drive Setup ===
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
CREDENTIALS_FILE = "credentials.json"  # OAuth2 credentials file
SPREADSHEET_ID = os.getenv("GOOGLE_SHEET_ID")
DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID")

# Check for required environment variables
if not SPREADSHEET_ID or not DRIVE_FOLDER_ID:
    print("ERROR: Missing required environment variables!")
    print("Please set GOOGLE_SHEET_ID and GOOGLE_DRIVE_FOLDER_ID in your .env file")
    sys.exit(1)

# GitHub Actions compatible authentication
try:
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    else:
        if not os.path.exists(CREDENTIALS_FILE):
            print(f"ERROR: {CREDENTIALS_FILE} not found!")
            print("Please add GOOGLE_CREDENTIALS as a GitHub secret")
            sys.exit(1)
        
        # For GitHub Actions, we use service account or pre-generated tokens
        # Since GitHub Actions can't do interactive OAuth, we'll use service account approach
        from google.oauth2 import service_account
        
        try:
            # Try service account authentication first
            creds = service_account.Credentials.from_service_account_file(
                CREDENTIALS_FILE, scopes=SCOPES)
        except Exception:
            # If not service account, try regular OAuth flow
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            
            # Check if we're in GitHub Actions (CI environment)
            if os.environ.get('GITHUB_ACTIONS'):
                print("ERROR: GitHub Actions detected but interactive OAuth not possible!")
                print("Please use a service account credentials.json instead of OAuth client credentials")
                print("Or run this locally first to generate token.json, then add it as a secret")
                sys.exit(1)
            else:
                # Local development - use local server
                creds = flow.run_local_server(port=0)
                
                # Save the credentials for the next run
                with open("token.json", "w") as token:
                    token.write(creds.to_json())

    gc = gspread.authorize(creds)
    print("✅ Google Sheets authentication successful")
    
except Exception as e:
    print(f"ERROR: Failed to authenticate with Google: {e}")
    sys.exit(1)

# Configure PyDrive authentication
try:
    gauth = GoogleAuth()
    
    # For GitHub Actions, we need to handle authentication differently
    if os.environ.get('GITHUB_ACTIONS'):
        # Use the same service account credentials for PyDrive
        gauth.LoadClientConfigFile(CREDENTIALS_FILE)
        # For service account, we can't use the normal flow
        # Instead, we'll use the gspread credentials
        print("Using service account for PyDrive in GitHub Actions")
        # We'll create a custom auth approach using the same creds
        gauth.credentials = creds
    else:
        # Local development
        gauth.LoadClientConfigFile(CREDENTIALS_FILE)
        if os.path.exists("pydrive_token.json"):
            gauth.LoadCredentialsFile("pydrive_token.json")
        if not gauth.credentials or gauth.access_token_expired:
            gauth.LocalWebserverAuth()
            gauth.SaveCredentialsFile("pydrive_token.json")
    
    drive = GoogleDrive(gauth)
    print("✅ Google Drive authentication successful")
    
except Exception as e:
    print(f"WARNING: Failed to setup PyDrive (continuing without Drive upload): {e}")
    drive = None


# === Selenium Setup - GitHub Actions Compatible ===
def get_driver(headless=True):
    chrome_options = Options()
    
    # GitHub Actions requires these specific options
    chrome_options.add_argument("--headless")  # Always headless in CI
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-plugins")
    chrome_options.add_argument("--disable-images")  # Save bandwidth
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    chrome_options.add_argument("--window-size=1920,1080")
    
    # Set user agent
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")

    try:
        # Check if we're in GitHub Actions
        if os.environ.get('GITHUB_ACTIONS'):
            print("Detected GitHub Actions environment")
            # GitHub Actions has chromium-browser installed
            service = Service('/usr/bin/chromedriver')
            driver = webdriver.Chrome(service=service, options=chrome_options)
        elif platform.system() == "Linux":
            # Generic Linux setup
            driver = webdriver.Chrome(options=chrome_options)
        else:
            # Windows/Mac
            driver = webdriver.Chrome(options=chrome_options)
        
        # Execute script to hide webdriver property
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        print(f"✅ Chrome driver initialized successfully")
        return driver
        
    except WebDriverException as e:
        print(f"ERROR: Failed to initialize Chrome driver: {e}")
        if os.environ.get('GITHUB_ACTIONS'):
            print("GitHub Actions Chrome setup failed - check if chromium-browser is installed correctly")
        else:
            print("Make sure Chrome and ChromeDriver are installed and in your PATH")
        raise


def upload_screenshot(file_path):
    if not drive:
        print("WARNING: Drive not available, skipping screenshot upload")
        return ""
        
    try:
        gfile = drive.CreateFile({"parents": [{"id": DRIVE_FOLDER_ID}]})
        gfile.SetContentFile(file_path)
        gfile.Upload()
        gfile.InsertPermission({"type": "anyone", "value": "anyone", "role": "reader"})
        return f"https://drive.google.com/file/d/{gfile['id']}/view?usp=drivesdk"
    except Exception as e:
        print(f"ERROR: Failed to upload screenshot: {e}")
        return ""


def scrape_sales():
    driver = None
    try:
        driver = get_driver()
        print(f"🚀 Starting scrape on: {platform.system()} - {platform.platform()}")
        
        driver.get("https://std.nest.net.np")

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
        
        print(f"\n📸 Taking screenshot for {today_date}...")
        driver.save_screenshot(daily_screenshot_path)
        print(f"Screenshot saved: {daily_screenshot_path}")
        
        # Upload screenshot to Drive (if available)
        screenshot_link = upload_screenshot(daily_screenshot_path) if drive else ""
        if screenshot_link:
            print(f"Screenshot uploaded: {screenshot_link}")
        
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

        return all_rows

    except Exception as e:
        print(f"ERROR in scrape_sales: {e}")
        import traceback
        traceback.print_exc()
        return []
    finally:
        if driver:
            driver.quit()


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
    print("🚀 Starting sales scraper (GitHub Actions compatible)...")
    print(f"Running on: {platform.system()} - {platform.platform()}")
    
    try:
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

    except Exception as e:
        print(f"ERROR in main: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()