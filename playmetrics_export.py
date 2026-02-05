"""
PlayMetrics Player Export Script

Automatically exports player data with parent/guardian contact information
from PlayMetrics to CSV format.

Features:
- Automated browser login with Selenium (headless Chrome)
- 2FA support with device remembering (only need to verify once)
- Captures authentication from network traffic
- Exports players, teams, and programs to timestamped CSV

Usage:
    1. Install dependencies: pip install -r requirements.txt
    2. Create .env file with credentials: copy .env.example .env
    3. Edit .env with your PlayMetrics email and password
    4. Run: python playmetrics_export.py

First run will prompt for 2FA code. Subsequent runs skip 2FA automatically.

Repository: https://github.com/tylercasey2263/playmetrics-export
"""

import csv
import json
import os
import time
from datetime import datetime
from pathlib import Path

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed, will use os.environ directly

# =============================================================================
# CONFIGURATION
# =============================================================================

CREDENTIALS = {
    "email": os.environ.get("PLAYMETRICS_EMAIL", "tylercasey2263@gmail.com"),
    "password": os.environ.get("PLAYMETRICS_PASSWORD", ""),
}

SCRIPT_DIR = Path(__file__).parent

# =============================================================================
# Browser-based Data Fetcher
# =============================================================================

def create_driver():
    """Create a Selenium WebDriver with network logging and persistent profile"""
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from webdriver_manager.chrome import ChromeDriverManager

    options = Options()
    options.add_argument('--headless=new')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')

    # Use a persistent Chrome profile to save cookies/"remember device" state
    profile_dir = SCRIPT_DIR / ".chrome_profile"
    profile_dir.mkdir(exist_ok=True)
    options.add_argument(f'--user-data-dir={profile_dir}')

    # Enable performance logging to capture network traffic
    options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )

    # Enable CDP network tracking
    driver.execute_cdp_cmd('Network.enable', {})

    return driver


def login_to_playmetrics(driver):
    """Log into PlayMetrics, handling 2FA if needed"""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    print("Navigating to PlayMetrics...")
    driver.get("https://playmetrics.com/login")
    time.sleep(3)

    # Check if already logged in (redirected away from login page)
    if "/login" not in driver.current_url:
        print("Already logged in! (session restored)")
        return

    # Wait for login form
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='email'], input[name='email'], input[placeholder*='mail']"))
        )
    except:
        # Might already be logged in
        if "/login" not in driver.current_url:
            print("Already logged in!")
            return
        raise

    time.sleep(1)

    # Fill login form
    print("Entering credentials...")
    email_field = driver.find_element(By.CSS_SELECTOR, "input[type='email'], input[name='email'], input[placeholder*='mail']")
    email_field.clear()
    email_field.send_keys(CREDENTIALS["email"])

    password_field = driver.find_element(By.CSS_SELECTOR, "input[type='password']")
    password_field.clear()
    password_field.send_keys(CREDENTIALS["password"])

    # Click login button
    try:
        login_button = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
    except:
        login_button = driver.find_element(By.XPATH, "//button[contains(text(), 'Log') or contains(text(), 'Sign')]")
    login_button.click()

    print("Logging in...")

    # Wait for page to change
    WebDriverWait(driver, 30).until(
        lambda d: "/login" not in d.current_url or "verification" in d.page_source.lower()
    )
    time.sleep(2)

    # Check if 2FA is required
    page_source = driver.page_source.lower()
    if "verification code" in page_source or "enter code" in page_source:
        print("\n2FA verification required!")
        verification_code = input("Enter the 6-digit verification code sent to your phone: ").strip()

        code_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='text'], input[type='number'], input[placeholder*='ode']"))
        )
        code_input.clear()
        code_input.send_keys(verification_code)

        # Check "Remember this device" if available
        try:
            remember_checkbox = driver.find_element(By.CSS_SELECTOR, "input[type='checkbox']")
            if not remember_checkbox.is_selected():
                remember_checkbox.click()
        except:
            pass

        # Click verify button
        try:
            verify_button = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
        except:
            verify_button = driver.find_element(By.XPATH, "//button[contains(text(), 'Verify')]")
        verify_button.click()

        # Wait for verification to complete
        WebDriverWait(driver, 30).until(
            lambda d: "verification" not in d.current_url.lower()
        )
        time.sleep(2)

    print("Login successful!")


def fetch_api_data(driver, endpoint, params=None):
    """Fetch data from PlayMetrics API using the browser's authenticated session"""

    # Build the URL with params
    url = f"https://api.playmetrics.com{endpoint}"
    if params:
        from urllib.parse import urlencode
        url += "?" + urlencode(params)

    # Use fetch() from within the page context - it will use the app's auth headers
    js_code = f"""
    return new Promise(async (resolve, reject) => {{
        try {{
            // Get the auth headers that the app uses
            // Look for them in the app's HTTP client or stored state
            let headers = {{}};

            // Try to find Firebase token in IndexedDB
            const getFirebaseToken = () => {{
                return new Promise((res) => {{
                    const request = indexedDB.open('firebaseLocalStorageDb');
                    request.onsuccess = (event) => {{
                        const db = event.target.result;
                        try {{
                            const tx = db.transaction('firebaseLocalStorage', 'readonly');
                            const store = tx.objectStore('firebaseLocalStorage');
                            const getAll = store.getAll();
                            getAll.onsuccess = () => {{
                                for (const item of getAll.result || []) {{
                                    if (item.value && item.value.stsTokenManager) {{
                                        res(item.value.stsTokenManager.accessToken);
                                        return;
                                    }}
                                }}
                                res(null);
                            }};
                            getAll.onerror = () => res(null);
                        }} catch(e) {{
                            res(null);
                        }}
                    }};
                    request.onerror = () => res(null);
                    setTimeout(() => res(null), 2000);
                }});
            }};

            const firebaseToken = await getFirebaseToken();
            if (!firebaseToken) {{
                reject('Could not get Firebase token');
                return;
            }}

            headers['firebase-token'] = firebaseToken;
            headers['Content-Type'] = 'application/json';
            headers['Accept'] = 'application/json';

            // Make the request
            const response = await fetch('{url}', {{
                method: 'GET',
                headers: headers,
                credentials: 'include'
            }});

            if (!response.ok) {{
                const text = await response.text();
                reject(`HTTP ${{response.status}}: ${{text}}`);
                return;
            }}

            const data = await response.json();
            resolve(JSON.stringify(data));
        }} catch (err) {{
            reject(err.toString());
        }}
    }});
    """

    try:
        result = driver.execute_script(js_code)
        return json.loads(result)
    except Exception as e:
        error_msg = str(e)
        if "access_key" in error_msg.lower():
            # The API needs pm-access-key header - we need to intercept how the app gets it
            print("  API requires access_key - trying alternative method...")
            return fetch_via_app_navigation(driver, endpoint)
        raise


def fetch_via_app_navigation(driver, endpoint):
    """Fetch data by navigating to the page and extracting from app state"""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    # Map endpoints to pages
    page_map = {
        "/players": "https://playmetrics.com/players",
        "/teams": "https://playmetrics.com/teams",
        "/program_admin/programs": "https://playmetrics.com/programs",
    }

    page_url = page_map.get(endpoint)
    if not page_url:
        raise ValueError(f"Unknown endpoint: {endpoint}")

    # Set up to capture API responses
    driver.execute_script("""
        window._apiResponses = {};
        const originalFetch = window.fetch;
        window.fetch = async function(url, options) {
            const response = await originalFetch.apply(this, arguments);
            if (url && url.includes && url.includes('api.playmetrics.com')) {
                try {
                    const clone = response.clone();
                    const data = await clone.json();
                    const endpoint = new URL(url).pathname;
                    window._apiResponses[endpoint] = data;
                } catch(e) {}
            }
            return response;
        };
    """)

    # Navigate to the page
    driver.get(page_url)
    time.sleep(5)  # Wait for API calls to complete

    # Get captured responses
    responses = driver.execute_script("return window._apiResponses;")

    # Find matching response
    for key, value in responses.items():
        if endpoint in key or key in endpoint:
            return value

    # If no direct match, return all responses for debugging
    if responses:
        return list(responses.values())[0]

    raise RuntimeError(f"Could not fetch data for {endpoint}")


def extract_headers_from_performance_log(driver):
    """Extract API request headers from Chrome's performance log"""
    headers = {}
    logs = driver.get_log('performance')

    api_requests_found = []

    for log in logs:
        try:
            message = json.loads(log['message'])['message']
            method = message.get('method', '')

            # Look for Network.requestWillBeSent events with our API
            if method == 'Network.requestWillBeSent':
                request = message['params'].get('request', {})
                url = request.get('url', '')

                if 'api.playmetrics.com' in url:
                    api_requests_found.append(url[:80])
                    req_headers = request.get('headers', {})

                    # Debug: print all header names for first API request
                    if len(api_requests_found) == 1:
                        print(f"    Headers in request: {list(req_headers.keys())}")

                    # Get the auth headers (check case-insensitive)
                    for key, value in req_headers.items():
                        key_lower = key.lower()
                        if key_lower in ['firebase-token', 'pm-access-key', 'build-version']:
                            headers[key_lower] = value

        except (json.JSONDecodeError, KeyError) as e:
            pass

    if api_requests_found:
        print(f"    Found {len(api_requests_found)} API requests in log")
    else:
        print(f"    No API requests found in {len(logs)} log entries")

    # Return with normalized keys
    result = {}
    if headers.get('firebase-token'):
        result['firebase-token'] = headers['firebase-token']
    if headers.get('pm-access-key'):
        result['pm-access-key'] = headers['pm-access-key']
    if headers.get('build-version'):
        result['build-version'] = headers['build-version']

    return result if result.get('firebase-token') else None


def make_api_call_with_headers(driver, endpoint, params, headers):
    """Make an API call using captured headers"""
    from urllib.parse import urlencode

    url = f"https://api.playmetrics.com{endpoint}"
    if params:
        url += "?" + urlencode(params)

    headers_json = json.dumps(headers)

    js_code = f"""
    return (async () => {{
        try {{
            const resp = await fetch('{url}', {{
                method: 'GET',
                headers: {headers_json},
                credentials: 'include'
            }});

            if (!resp.ok) {{
                const text = await resp.text();
                return JSON.stringify({{error: resp.status, message: text}});
            }}

            return await resp.text();
        }} catch (err) {{
            return JSON.stringify({{error: err.toString()}});
        }}
    }})();
    """

    result = driver.execute_script(js_code)
    return json.loads(result) if result else None


def fetch_all_data_via_browser(driver):
    """Fetch all required data by intercepting the app's API calls"""
    data = {
        "players": None,
        "teams": None,
        "programs": None
    }

    # Clear performance logs
    driver.get_log('performance')

    # Navigate to players page - this will trigger API calls
    print("Loading PlayMetrics players page...")
    driver.get("https://playmetrics.com/players")
    time.sleep(6)

    # Extract headers from the network requests that just happened
    print("  Extracting auth headers from network traffic...")
    headers = extract_headers_from_performance_log(driver)

    if headers:
        print(f"  Got headers: {list(headers.keys())}")

        # Add standard headers
        headers['Accept'] = 'application/json'
        headers['Content-Type'] = 'application/json'

        # Now make API calls with the captured headers
        print("Fetching players...")
        players_result = make_api_call_with_headers(
            driver,
            "/players",
            {"data": json.dumps({"include_archived": False}), "populate": "team_players,users,program_ids"},
            headers
        )

        if players_result and 'error' not in players_result:
            data['players'] = players_result
            count = len(players_result) if isinstance(players_result, list) else len(players_result.get('data', []))
            print(f"    Got players data ({count} records)")
        else:
            print(f"    Players API failed: {players_result}")

        print("Fetching teams...")
        teams_result = make_api_call_with_headers(
            driver,
            "/teams",
            {"populate": "num_players"},
            headers
        )
        if teams_result and 'error' not in teams_result:
            data['teams'] = teams_result
            print(f"    Got teams data")

        print("Fetching programs...")
        programs_result = make_api_call_with_headers(
            driver,
            "/program_admin/programs",
            {"populate": "prune"},
            headers
        )
        if programs_result and 'error' not in programs_result:
            data['programs'] = programs_result
            print(f"    Got programs data")

    else:
        print("  Could not extract headers from network traffic")
        print("  Trying to capture data from page directly...")

        # Alternative: intercept responses from network log
        logs = driver.get_log('performance')
        for log in logs:
            try:
                message = json.loads(log['message'])['message']
                if message['method'] == 'Network.responseReceived':
                    url = message['params']['response']['url']
                    if 'api.playmetrics.com/players' in url:
                        request_id = message['params']['requestId']
                        try:
                            body = driver.execute_cdp_cmd('Network.getResponseBody', {'requestId': request_id})
                            if body and body.get('body'):
                                data['players'] = json.loads(body['body'])
                                print(f"    Got players data from network capture")
                        except:
                            pass
            except:
                pass

    return data


# =============================================================================
# Data Processing
# =============================================================================

def build_team_lookup(teams_data):
    """Build a lookup dict of team_id -> team_name"""
    lookup = {}
    if not teams_data:
        return lookup
    teams = teams_data if isinstance(teams_data, list) else teams_data.get("data", teams_data.get("teams", []))
    for team in teams:
        team_id = team.get("id") or team.get("team_id")
        team_name = team.get("name") or team.get("team_name", "Unknown Team")
        if team_id:
            lookup[team_id] = team_name
    return lookup


def build_program_lookup(programs_data):
    """Build a lookup dict of program_id -> program_name"""
    lookup = {}
    if not programs_data:
        return lookup
    programs = programs_data if isinstance(programs_data, list) else programs_data.get("data", programs_data.get("programs", []))
    for program in programs:
        program_id = program.get("id") or program.get("program_id")
        program_name = program.get("name") or program.get("program_name", "Unknown Program")
        if program_id:
            lookup[program_id] = program_name
    return lookup


def extract_player_data(player, team_lookup, program_lookup):
    """Extract relevant fields from a player record"""
    player_id = player.get("id") or player.get("player_id", "")
    first_name = player.get("first_name") or player.get("firstName") or player.get("fname", "")
    last_name = player.get("last_name") or player.get("lastName") or player.get("lname", "")

    if not first_name and not last_name:
        full_name = player.get("name") or player.get("player_name", "")
        parts = full_name.split(" ", 1)
        first_name = parts[0] if parts else ""
        last_name = parts[1] if len(parts) > 1 else ""

    birth_date = player.get("birth_date") or player.get("birthDate") or player.get("dob", "")
    gender = player.get("gender") or player.get("sex", "")

    # Team info
    team_names = []
    team_players = player.get("team_players") or player.get("teams") or []
    if isinstance(team_players, list):
        for tp in team_players:
            team_id = tp.get("team_id") or tp.get("teamId")
            if team_id and team_id in team_lookup:
                team_names.append(team_lookup[team_id])
            elif tp.get("team_name") or tp.get("name"):
                team_names.append(tp.get("team_name") or tp.get("name"))

    # Program info
    program_names = []
    program_ids = player.get("program_ids") or player.get("programs") or []
    if isinstance(program_ids, list):
        for pid in program_ids:
            if isinstance(pid, dict):
                pid = pid.get("id") or pid.get("program_id")
            if pid and pid in program_lookup:
                program_names.append(program_lookup[pid])

    # Contact info from users (parents/guardians)
    contacts = []
    users = player.get("users") or player.get("contacts") or player.get("guardians") or []
    if isinstance(users, list):
        for user in users:
            contact = {
                "name": "",
                "email": "",
                "phone": "",
                "relationship": ""
            }
            contact["name"] = (
                user.get("name") or
                f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() or
                f"{user.get('firstName', '')} {user.get('lastName', '')}".strip()
            )
            contact["email"] = user.get("email") or user.get("email_address", "")
            contact["phone"] = (
                user.get("phone") or
                user.get("phone_number") or
                user.get("mobile") or
                user.get("cell", "")
            )
            contact["relationship"] = user.get("relationship") or user.get("role") or user.get("type", "")

            if contact["name"] or contact["email"] or contact["phone"]:
                contacts.append(contact)

    return {
        "player_id": player_id,
        "first_name": first_name,
        "last_name": last_name,
        "birth_date": birth_date,
        "gender": gender,
        "teams": "; ".join(team_names) if team_names else "",
        "programs": "; ".join(program_names) if program_names else "",
        "contacts": contacts,
    }


# =============================================================================
# CSV Export
# =============================================================================

def export_to_csv(players_data, team_lookup, program_lookup, filename=None, max_contacts=4):
    """Export player data to CSV with all contacts on one row"""
    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = SCRIPT_DIR / f"playmetrics_players_{timestamp}.csv"

    rows = []
    players = players_data if isinstance(players_data, list) else players_data.get("data", players_data.get("players", []))

    for player in players:
        player_info = extract_player_data(player, team_lookup, program_lookup)

        row = {
            "Player ID": player_info["player_id"],
            "Player First Name": player_info["first_name"],
            "Player Last Name": player_info["last_name"],
            "Birth Date": player_info["birth_date"],
            "Gender": player_info["gender"],
            "Program(s)": player_info["programs"],
        }

        contacts = player_info["contacts"] or []
        for i in range(max_contacts):
            contact_num = i + 1
            if i < len(contacts):
                row[f"Parent {contact_num} Name"] = contacts[i]["name"]
                row[f"Parent {contact_num} Email"] = contacts[i]["email"]
            else:
                row[f"Parent {contact_num} Name"] = ""
                row[f"Parent {contact_num} Email"] = ""

        rows.append(row)

    if rows:
        fieldnames = list(rows[0].keys())
        with open(filename, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        print(f"\nExported {len(rows)} players to {filename}")
    else:
        print("No player data to export!")

    return filename


# =============================================================================
# Main
# =============================================================================

def main():
    print("PlayMetrics Player Export")
    print("=" * 40)

    if not CREDENTIALS["password"]:
        print("\nERROR: Please set your password!")
        print("\nOption 1: Create a .env file in the same directory:")
        print("  PLAYMETRICS_EMAIL=your_email@example.com")
        print("  PLAYMETRICS_PASSWORD=your_password")
        print("\nOption 2: Set environment variables:")
        print("  set PLAYMETRICS_PASSWORD=your_password  (Windows)")
        print("  export PLAYMETRICS_PASSWORD=your_password  (Mac/Linux)")
        return

    driver = None
    try:
        # Import selenium here to give better error message if missing
        try:
            from selenium import webdriver
        except ImportError:
            print("\nMissing dependencies! Install with:")
            print("  pip install selenium webdriver-manager")
            return

        print("\nLaunching browser...")
        driver = create_driver()

        # Login to PlayMetrics
        login_to_playmetrics(driver)

        # Fetch all data through the browser
        print("\nFetching data from PlayMetrics...")
        data = fetch_all_data_via_browser(driver)

        if not data.get('players'):
            print("\nERROR: Could not fetch player data")
            print("The app may have changed. Try running with visible browser for debugging.")
            return

        # Build lookups
        team_lookup = build_team_lookup(data.get('teams'))
        program_lookup = build_program_lookup(data.get('programs'))

        print(f"Found {len(team_lookup)} teams")
        print(f"Found {len(program_lookup)} programs")

        # Export to CSV
        export_to_csv(data['players'], team_lookup, program_lookup)

    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()

        # Save screenshot for debugging
        if driver:
            try:
                screenshot_path = SCRIPT_DIR / "error_screenshot.png"
                driver.save_screenshot(str(screenshot_path))
                print(f"Screenshot saved to: {screenshot_path}")
            except:
                pass

    finally:
        if driver:
            driver.quit()


if __name__ == "__main__":
    main()
