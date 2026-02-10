"""
PlayMetrics Data Export Script

Exports player, team, program, tournament, and game data from PlayMetrics
to CSV format using direct API calls. No browser required.

Authentication is handled entirely via Firebase REST API:
- First run: signs in with email/password, prompts for 2FA code on the command line
- Subsequent runs: refreshes the saved token automatically (no 2FA needed)

Usage:
    python playmetrics_export.py                  # Export all data types
    python playmetrics_export.py --players        # Export only players
    python playmetrics_export.py --teams --games  # Export teams and games
    python playmetrics_export.py -p -t            # Short flags work too
"""

import argparse
import csv
import json
import os
import sys
import time
import requests as http_client
from datetime import datetime
from pathlib import Path

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# =============================================================================
# CONFIGURATION
# =============================================================================

CREDENTIALS = {
    "email": os.environ.get("PLAYMETRICS_EMAIL", "tylercasey2263@gmail.com"),
    "password": os.environ.get("PLAYMETRICS_PASSWORD", ""),
}

SCRIPT_DIR = Path(__file__).parent

# Auth tokens persisted across runs
AUTH_FILE = Path(os.environ.get("LOCALAPPDATA", str(SCRIPT_DIR))) / "playmetrics_auth.json"

# Firebase config (public client-side values from playmetrics.com)
FIREBASE_API_KEY = "AIzaSyBEB_rFRGuLJja2vzeDCa7J1NZp0E7RN4U"
BUILD_VERSION = "5fac58cc34a04c5db38ff207d38d42409231c684"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


# =============================================================================
# Firebase REST API Authentication (no browser needed)
# =============================================================================

def firebase_sign_in(email, password):
    """Sign in with email/password via Firebase REST API."""
    resp = http_client.post(
        f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_API_KEY}",
        json={
            "email": email,
            "password": password,
            "returnSecureToken": True,
        },
        headers={"User-Agent": USER_AGENT},
        timeout=15,
    )
    return resp.status_code, resp.json()


def firebase_mfa_start(mfa_pending_credential, mfa_enrollment_id):
    """Request SMS verification code for MFA."""
    resp = http_client.post(
        f"https://identitytoolkit.googleapis.com/v2/accounts/mfaSignIn:start?key={FIREBASE_API_KEY}",
        json={
            "mfaPendingCredential": mfa_pending_credential,
            "mfaEnrollmentId": mfa_enrollment_id,
            "phoneSignInInfo": {},
        },
        headers={"User-Agent": USER_AGENT},
        timeout=15,
    )
    return resp.status_code, resp.json()


def firebase_mfa_finalize(mfa_pending_credential, session_info, code):
    """Submit the 2FA code and get final auth tokens."""
    resp = http_client.post(
        f"https://identitytoolkit.googleapis.com/v2/accounts/mfaSignIn:finalize?key={FIREBASE_API_KEY}",
        json={
            "mfaPendingCredential": mfa_pending_credential,
            "phoneVerificationInfo": {
                "sessionInfo": session_info,
                "code": code,
            },
        },
        headers={"User-Agent": USER_AGENT},
        timeout=15,
    )
    return resp.status_code, resp.json()


def firebase_refresh_token(refresh_token):
    """Get a new ID token using a refresh token."""
    resp = http_client.post(
        f"https://securetoken.googleapis.com/v1/token?key={FIREBASE_API_KEY}",
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
        headers={"User-Agent": USER_AGENT},
        timeout=15,
    )
    if resp.status_code == 200:
        data = resp.json()
        return data.get("id_token"), data.get("refresh_token")
    return None, None


# =============================================================================
# PlayMetrics Backend Auth (separate from Firebase — returns access_key)
# =============================================================================

def pm_login(firebase_token, verified2fa=""):
    """Login to PlayMetrics backend. Returns user data including access_key
    if verified2fa is valid, or needs_2fa=true if 2FA is required."""
    resp = http_client.post(
        "https://api.playmetrics.com/firebase/user/login",
        json={
            "current_role_id": "",
            "verified2fa": verified2fa,
        },
        headers={
            "firebase-token": firebase_token,
            "build-version": BUILD_VERSION,
            "Origin": "https://playmetrics.com",
            "Referer": "https://playmetrics.com/",
            "User-Agent": USER_AGENT,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        timeout=15,
    )
    return resp.status_code, resp.json()


def pm_2fa_send_code(firebase_token):
    """Request PlayMetrics to send a 2FA verification code via SMS."""
    resp = http_client.post(
        "https://api.playmetrics.com/firebase/user/2fa/send_code",
        json={},
        headers={
            "firebase-token": firebase_token,
            "build-version": BUILD_VERSION,
            "Origin": "https://playmetrics.com",
            "Referer": "https://playmetrics.com/",
            "User-Agent": USER_AGENT,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        timeout=15,
    )
    return resp.status_code, resp.json()


def pm_2fa_validate(firebase_token, token, code, remember_device=True):
    """Validate the 2FA code. Returns access_key and verified2fa token."""
    resp = http_client.post(
        "https://api.playmetrics.com/firebase/user/2fa/validate",
        json={
            "token": token,
            "validation_code": code,
            "remember_device": remember_device,
        },
        headers={
            "firebase-token": firebase_token,
            "build-version": BUILD_VERSION,
            "Origin": "https://playmetrics.com",
            "Referer": "https://playmetrics.com/",
            "User-Agent": USER_AGENT,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        timeout=15,
    )
    return resp.status_code, resp.json()


# =============================================================================
# Auth Token Management
# =============================================================================

def load_auth():
    """Load saved auth tokens from disk."""
    if AUTH_FILE.exists():
        try:
            return json.loads(AUTH_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return None
    return None


def save_auth(auth):
    """Save auth tokens to disk for future runs."""
    AUTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    AUTH_FILE.write_text(json.dumps(auth, indent=2))


def get_valid_auth():
    """Get valid auth. Flow:
    1. Refresh Firebase token (if saved)
    2. Login to PlayMetrics backend with verified2fa cookie
    3. If 2FA needed, prompt on command line
    4. Save access_key + verified2fa for future runs
    """
    auth = load_auth()

    # Step 1: Get a fresh Firebase token
    if auth and auth.get("refresh_token"):
        print("Refreshing Firebase token...")
        new_id_token, new_refresh_token = firebase_refresh_token(auth["refresh_token"])
        if new_id_token:
            auth["firebase_token"] = new_id_token
            auth["refresh_token"] = new_refresh_token
            print("  Firebase token refreshed")
        else:
            print("  Refresh failed, doing full Firebase sign-in...")
            auth = _firebase_login()
            if not auth:
                return None
    else:
        print("No saved tokens, doing full sign-in...")
        auth = _firebase_login()
        if not auth:
            return None

    # Step 2: If we already have a valid access_key, test it
    if auth.get("pm_access_key"):
        if test_api(auth):
            save_auth(auth)
            print("Authentication successful (saved credentials still valid)")
            return auth
        print("  Saved access_key expired, re-authenticating with PlayMetrics...")

    # Step 3: Login to PlayMetrics backend
    auth = _pm_authenticate(auth)
    if not auth:
        return None

    save_auth(auth)
    return auth


def _firebase_login():
    """Do a fresh Firebase email/password sign-in. Handles Firebase MFA if needed."""
    print("Signing in to Firebase...")
    status, result = firebase_sign_in(CREDENTIALS["email"], CREDENTIALS["password"])

    if "mfaPendingCredential" in result:
        return _handle_firebase_mfa(result)
    elif "idToken" in result and result.get("idToken"):
        print("  Firebase sign-in successful")
        return {
            "firebase_token": result["idToken"],
            "refresh_token": result["refreshToken"],
            "captured_at": datetime.now().isoformat(),
        }
    elif result.get("error"):
        msg = result["error"].get("message", "Unknown error")
        if "MFA" in msg.upper() or "SECOND_FACTOR" in msg.upper():
            for detail in result["error"].get("errors", []):
                if "mfaPendingCredential" in str(detail):
                    return _handle_firebase_mfa(detail)
            print(f"Firebase MFA required but unexpected format: {msg}")
        else:
            print(f"Firebase login failed: {msg}")
            if "INVALID" in msg:
                print("Check your email and password in the .env file.")
        return None
    else:
        print(f"Unexpected Firebase response: {json.dumps(result, indent=2)}")
        return None


def _handle_firebase_mfa(result):
    """Handle Firebase-level MFA (if enabled)."""
    mfa_pending = result["mfaPendingCredential"]
    mfa_info = result.get("mfaInfo", [])
    if not mfa_info:
        print("Firebase MFA required but no MFA info returned")
        return None

    mfa = mfa_info[0]
    phone = mfa.get("phoneInfo", mfa.get("unobfuscatedPhoneInfo", "your phone"))
    enrollment_id = mfa.get("mfaEnrollmentId")

    print(f"  Firebase 2FA required (phone: {phone})")
    print("  Sending verification code...")

    status, start_result = firebase_mfa_start(mfa_pending, enrollment_id)
    if start_result.get("error"):
        print(f"  Failed: {start_result['error'].get('message', 'Unknown')}")
        return None

    session_info = start_result.get("phoneResponseInfo", {}).get("sessionInfo")
    if not session_info:
        print(f"  No session info returned: {json.dumps(start_result, indent=2)}")
        return None

    print("  Code sent!")
    code = input("Enter the 6-digit Firebase verification code: ").strip()
    if not code:
        return None

    status, final_result = firebase_mfa_finalize(mfa_pending, session_info, code)
    if final_result.get("error"):
        print(f"  Verification failed: {final_result['error'].get('message', 'Unknown')}")
        return None

    id_token = final_result.get("idToken")
    refresh_token = final_result.get("refreshToken")
    if not id_token or not refresh_token:
        print(f"  Unexpected response: {json.dumps(final_result, indent=2)}")
        return None

    print("  Firebase 2FA verified!")
    return {
        "firebase_token": id_token,
        "refresh_token": refresh_token,
        "captured_at": datetime.now().isoformat(),
    }


def _pm_authenticate(auth):
    """Login to PlayMetrics backend and handle PlayMetrics 2FA if needed."""
    verified2fa = auth.get("verified2fa", "")

    print("Logging in to PlayMetrics backend...")
    status, result = pm_login(auth["firebase_token"], verified2fa)

    if status != 200:
        print(f"  PlayMetrics login failed ({status}): {json.dumps(result, indent=2)[:300]}")
        return None

    # Check if PlayMetrics needs its own 2FA
    if result.get("needs_2fa"):
        print("\nPlayMetrics 2FA verification required!")
        print("Sending verification code to your phone...")

        status, send_result = pm_2fa_send_code(auth["firebase_token"])
        if status != 200:
            print(f"  Failed to send code ({status}): {json.dumps(send_result, indent=2)[:300]}")
            return None

        # send_result contains a token needed for validation
        tfa_token = send_result.get("token", "")
        if not tfa_token:
            print(f"  No token in send_code response: {json.dumps(send_result, indent=2)[:300]}")
            return None

        print("Code sent!")
        code = input("Enter the 6-digit verification code: ").strip()
        if not code:
            print("No code entered.")
            return None

        status, validate_result = pm_2fa_validate(
            auth["firebase_token"], tfa_token, code, remember_device=True
        )
        if status != 200:
            print(f"  Validation failed ({status}): {json.dumps(validate_result, indent=2)[:300]}")
            return None

        # Extract access_key and verified2fa from the validation response
        access_key = validate_result.get("access_key", "")
        new_verified2fa = validate_result.get("verified2fa", "")

        if not access_key:
            # access_key might be nested in user data
            user = validate_result.get("user", validate_result)
            access_key = user.get("access_key", "")

        if access_key:
            auth["pm_access_key"] = access_key
            auth["verified2fa"] = new_verified2fa
            print("2FA verified! Access key obtained.")
        else:
            print(f"  No access_key in response: {json.dumps(validate_result, indent=2)[:500]}")
            return None
    else:
        # No 2FA needed — extract access_key from login response
        access_key = result.get("access_key", "")
        if not access_key:
            user = result.get("user", result)
            access_key = user.get("access_key", "")

        if access_key:
            auth["pm_access_key"] = access_key
            print("  Access key obtained (no 2FA needed)")
        else:
            print(f"  No access_key in login response. Keys: {list(result.keys())}")
            print(f"  Response: {json.dumps(result, indent=2)[:500]}")
            return None

    # Verify it works
    if test_api(auth):
        print("PlayMetrics API access confirmed!")
    else:
        print("WARNING: API test still failing after obtaining access_key")

    return auth


# =============================================================================
# Direct API Client
# =============================================================================

def build_headers(auth):
    """Build API request headers from auth data."""
    headers = {
        "firebase-token": auth.get("firebase_token", ""),
        "build-version": auth.get("build_version", BUILD_VERSION),
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
        "Origin": "https://playmetrics.com",
        "Referer": "https://playmetrics.com/",
    }
    if auth.get("pm_access_key"):
        headers["pm-access-key"] = auth["pm_access_key"]
    return headers


def test_api(auth):
    """Quick test to verify auth tokens work."""
    try:
        resp = http_client.get(
            "https://api.playmetrics.com/teams",
            params={"populate": "num_players"},
            headers=build_headers(auth),
            timeout=10,
        )
        if resp.status_code != 200:
            print(f"  API test returned {resp.status_code}: {resp.text[:200]}")
        return resp.status_code == 200
    except Exception as e:
        print(f"  API test error: {e}")
        return False


def api_get(endpoint, params, auth):
    """Make a GET request to the PlayMetrics API."""
    url = f"https://api.playmetrics.com{endpoint}"
    resp = http_client.get(url, params=params, headers=build_headers(auth), timeout=30)
    if resp.status_code != 200:
        print(f"    Response {resp.status_code}: {resp.text[:300]}")
    resp.raise_for_status()
    return resp.json()


def fetch_data(auth, types):
    """Fetch requested data types via direct API calls.

    Args:
        auth: Auth tokens dict.
        types: Set of data type names to fetch (e.g. {"players", "teams"}).
    """
    data = {}

    # Players need teams/programs for lookups, so fetch those if players are requested
    need_teams = "teams" in types or "players" in types
    need_programs = "programs" in types or "players" in types

    if "players" in types:
        print("Fetching players...")
        try:
            data["players"] = api_get("/players", {
                "data": json.dumps({"include_archived": False}),
                "populate": "team_players,users,program_ids",
            }, auth)
            count = len(data["players"]) if isinstance(data["players"], list) else len(data["players"].get("data", []))
            print(f"  Got {count} players")
        except Exception as e:
            print(f"  Failed: {e}")

    if need_teams:
        print("Fetching teams...")
        try:
            data["teams"] = api_get("/teams", {"populate": "num_players"}, auth)
            count = len(data["teams"]) if isinstance(data["teams"], list) else "?"
            print(f"  Got teams data ({count})")
        except Exception as e:
            print(f"  Failed: {e}")

    if need_programs:
        print("Fetching programs...")
        try:
            data["programs"] = api_get("/program_admin/programs", {"populate": "prune"}, auth)
            print(f"  Got programs data")
        except Exception as e:
            print(f"  Failed: {e}")

    if "tournaments" in types:
        print("Fetching tournaments...")
        for endpoint in ["/tournaments", "/events", "/program_admin/events", "/program_admin/tournaments"]:
            try:
                result = api_get(endpoint, {}, auth)
                data["tournaments"] = result
                print(f"  Got tournaments (via {endpoint})")
                break
            except:
                pass
        if "tournaments" not in data:
            print("  No tournament endpoint found (tried /tournaments, /events, etc.)")

    if "games" in types:
        print("Fetching games...")
        for endpoint in ["/games", "/matches", "/schedule", "/program_admin/games", "/program_admin/schedule"]:
            try:
                result = api_get(endpoint, {}, auth)
                data["games"] = result
                print(f"  Got games (via {endpoint})")
                break
            except:
                pass
        if "games" not in data:
            print("  No games endpoint found (tried /games, /matches, etc.)")

    return data


# =============================================================================
# Data Processing
# =============================================================================

def build_team_lookup(teams_data):
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

    team_names = []
    team_players = player.get("team_players") or player.get("teams") or []
    if isinstance(team_players, list):
        for tp in team_players:
            team_id = tp.get("team_id") or tp.get("teamId")
            if team_id and team_id in team_lookup:
                team_names.append(team_lookup[team_id])
            elif tp.get("team_name") or tp.get("name"):
                team_names.append(tp.get("team_name") or tp.get("name"))

    program_names = []
    program_ids = player.get("program_ids") or player.get("programs") or []
    if isinstance(program_ids, list):
        for pid in program_ids:
            if isinstance(pid, dict):
                pid = pid.get("id") or pid.get("program_id")
            if pid and pid in program_lookup:
                program_names.append(program_lookup[pid])

    contacts = []
    users = player.get("users") or player.get("contacts") or player.get("guardians") or []
    if isinstance(users, list):
        for user in users:
            contact = {
                "name": (
                    user.get("name") or
                    f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() or
                    f"{user.get('firstName', '')} {user.get('lastName', '')}".strip()
                ),
                "email": user.get("email") or user.get("email_address", ""),
                "phone": (
                    user.get("phone") or user.get("phone_number") or
                    user.get("mobile") or user.get("cell", "")
                ),
                "relationship": user.get("relationship") or user.get("role") or user.get("type", ""),
            }
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

def export_players_csv(players_data, team_lookup, program_lookup, max_contacts=4):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = SCRIPT_DIR / f"playmetrics_players_{timestamp}.csv"

    rows = []
    players = players_data if isinstance(players_data, list) else players_data.get("data", players_data.get("players", []))

    for player in players:
        info = extract_player_data(player, team_lookup, program_lookup)
        row = {
            "Player ID": info["player_id"],
            "First Name": info["first_name"],
            "Last Name": info["last_name"],
            "Birth Date": info["birth_date"],
            "Gender": info["gender"],
            "Teams": info["teams"],
            "Program(s)": info["programs"],
        }
        contacts = info["contacts"] or []
        for i in range(max_contacts):
            n = i + 1
            if i < len(contacts):
                row[f"Parent {n} Name"] = contacts[i]["name"]
                row[f"Parent {n} Email"] = contacts[i]["email"]
                row[f"Parent {n} Phone"] = contacts[i]["phone"]
            else:
                row[f"Parent {n} Name"] = ""
                row[f"Parent {n} Email"] = ""
                row[f"Parent {n} Phone"] = ""
        rows.append(row)

    if rows:
        fieldnames = list(rows[0].keys())
        with open(filename, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        print(f"  Exported {len(rows)} players -> {filename}")
    else:
        print("  No player data to export!")
    return filename


def export_generic_csv(data, name):
    if not data:
        return None
    items = data if isinstance(data, list) else data.get("data", data.get(name, []))
    if not items or not isinstance(items, list):
        return None

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = SCRIPT_DIR / f"playmetrics_{name}_{timestamp}.csv"

    rows = []
    for item in items:
        row = {}
        for key, value in item.items():
            if isinstance(value, (dict, list)):
                row[key] = json.dumps(value)
            else:
                row[key] = value
        rows.append(row)

    if rows:
        fieldnames = list(dict.fromkeys(k for row in rows for k in row))
        with open(filename, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(rows)
        print(f"  Exported {len(rows)} {name} -> {filename}")
    return filename


# =============================================================================
# Main
# =============================================================================

def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Export data from PlayMetrics to CSV.",
        epilog="If no flags are specified, all data types are exported.",
    )
    parser.add_argument("-p", "--players", action="store_true", help="Export players")
    parser.add_argument("-t", "--teams", action="store_true", help="Export teams")
    parser.add_argument("-r", "--programs", action="store_true", help="Export programs")
    parser.add_argument("-n", "--tournaments", action="store_true", help="Export tournaments")
    parser.add_argument("-g", "--games", action="store_true", help="Export games")
    return parser.parse_args()


ALL_TYPES = {"players", "teams", "programs", "tournaments", "games"}


def main():
    args = parse_args()

    # If no specific flags, export everything
    requested = set()
    for name in ALL_TYPES:
        if getattr(args, name, False):
            requested.add(name)
    if not requested:
        requested = ALL_TYPES.copy()

    print("PlayMetrics Data Export")
    print("=" * 40)
    print(f"Exporting: {', '.join(sorted(requested))}")

    if not CREDENTIALS["password"]:
        print("\nERROR: Please set your password!")
        print("Create a .env file:")
        print("  PLAYMETRICS_EMAIL=your_email@example.com")
        print("  PLAYMETRICS_PASSWORD=your_password")
        return

    # Authenticate (refresh token or full login with 2FA prompt)
    auth = get_valid_auth()
    if not auth:
        print("\nAuthentication failed.")
        return

    # Fetch requested data via direct API calls
    print("\nFetching data from PlayMetrics API...")
    data = fetch_data(auth, requested)

    # Build lookups (needed for player export)
    team_lookup = build_team_lookup(data.get("teams"))
    program_lookup = build_program_lookup(data.get("programs"))

    # Export
    print("\nExporting...")
    exported = 0

    if "players" in requested and data.get("players"):
        export_players_csv(data["players"], team_lookup, program_lookup)
        exported += 1

    if "teams" in requested and data.get("teams"):
        export_generic_csv(data["teams"], "teams")
        exported += 1

    if "programs" in requested and data.get("programs"):
        export_generic_csv(data["programs"], "programs")
        exported += 1

    if "tournaments" in requested and data.get("tournaments"):
        export_generic_csv(data["tournaments"], "tournaments")
        exported += 1

    if "games" in requested and data.get("games"):
        export_generic_csv(data["games"], "games")
        exported += 1

    if exported == 0:
        print("  No data to export.")
        print(f"  Try deleting auth file to force re-login: del \"{AUTH_FILE}\"")
    else:
        print(f"\nDone! Exported {exported} file(s).")


if __name__ == "__main__":
    main()
