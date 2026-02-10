# PlayMetrics Data Export

A Python tool to export player, team, program, tournament, and game data from PlayMetrics to CSV. Uses direct API calls with no browser required.

## Features

- **No browser needed** - Authenticates entirely via REST API (Firebase + PlayMetrics backend)
- **Command-line 2FA** - Prompts for verification code in the terminal when needed
- **Persistent auth** - Saves tokens locally so 2FA is only needed once (~90 days)
- **Automatic token refresh** - Firebase tokens are refreshed automatically on each run
- **Complete data export** - Players with parent/guardian contacts, teams, programs, tournaments, and games

## Requirements

- Python 3.8 or higher
- A PlayMetrics account with admin access

## Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/tylercasey2263/playmetrics-export.git
   cd playmetrics-export
   ```

2. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up your credentials:**
   ```bash
   # Windows
   copy .env.example .env

   # Mac/Linux
   cp .env.example .env
   ```

4. **Edit `.env` with your PlayMetrics login:**
   ```
   PLAYMETRICS_EMAIL=your_email@example.com
   PLAYMETRICS_PASSWORD=your_password
   ```

## Usage

```bash
python playmetrics_export.py
```

### First Run

On the first run, the script will:
1. Sign in to Firebase with your email/password
2. Authenticate with the PlayMetrics backend
3. Send a 2FA code to your phone and prompt you to enter it
4. Save auth tokens locally (valid for ~90 days)
5. Fetch all data and export to CSV

```
PlayMetrics Data Export
========================================
No saved tokens, doing full sign-in...
Signing in to Firebase...
  Firebase sign-in successful
Logging in to PlayMetrics backend...

PlayMetrics 2FA verification required!
Sending verification code to your phone...
Code sent!
Enter the 6-digit verification code: 123456
2FA verified! Access key obtained.
PlayMetrics API access confirmed!
Authentication saved for future runs!

Fetching data from PlayMetrics API...
Fetching players...
  Got 1891 players
Fetching teams...
  Got teams data (212)
Fetching programs...
  Got programs data
...

Exporting...
  Exported 1891 players -> playmetrics_players_20260209_140500.csv

Done!
```

### Subsequent Runs

After the first run, no 2FA is needed. The script refreshes tokens automatically:

```
PlayMetrics Data Export
========================================
Refreshing Firebase token...
  Firebase token refreshed
Authentication successful (saved credentials still valid)

Fetching data from PlayMetrics API...
...
Done!
```

### Scheduling / Automation

Since no browser or user interaction is needed after the first run, you can schedule the script with Windows Task Scheduler, cron, or any automation tool:

```bash
# Windows Task Scheduler action:
python C:\path\to\playmetrics_export.py

# Linux/Mac cron:
0 6 * * * python /path/to/playmetrics_export.py
```

The `verified2fa` token lasts ~90 days. If it expires, the script will prompt for a new 2FA code on the next interactive run.

## Output

### Players CSV

The main export includes player details and up to 4 parent/guardian contacts:

| Column | Description |
|--------|-------------|
| Player ID | Unique player identifier |
| First Name | Player's first name |
| Last Name | Player's last name |
| Birth Date | Player's date of birth |
| Gender | Player's gender |
| Teams | Assigned teams (semicolon-separated) |
| Program(s) | Enrolled programs (semicolon-separated) |
| Parent 1-4 Name | Contact name |
| Parent 1-4 Email | Contact email |
| Parent 1-4 Phone | Contact phone number |

### Tournaments & Games CSV

If tournament and game endpoints are available, they are exported as separate CSV files with all fields from the API response.

## How It Works

### Authentication Flow

The script uses a two-layer authentication system, both handled via REST API:

```
1. Firebase Auth (email/password)
   POST identitytoolkit.googleapis.com/v1/accounts:signInWithPassword
   -> Returns Firebase ID token + refresh token

2. PlayMetrics Backend Auth (2FA + access key)
   POST api.playmetrics.com/firebase/user/login
   -> If needs_2fa: true
      POST /firebase/user/2fa/send_code  (sends SMS)
      POST /firebase/user/2fa/validate   (returns access_key + verified2fa)
   -> If needs_2fa: false (verified2fa cookie valid)
      Returns access_key directly

3. API Calls
   GET api.playmetrics.com/players
   Headers: firebase-token, pm-access-key, build-version
```

### Token Persistence

Auth tokens are saved to `%LOCALAPPDATA%\playmetrics_auth.json`:

| Token | Purpose | Lifetime |
|-------|---------|----------|
| `refresh_token` | Refreshes Firebase ID tokens | Long-lived (months) |
| `firebase_token` | Authenticates with Firebase | 1 hour (auto-refreshed) |
| `pm_access_key` | Authenticates API requests | Per-session |
| `verified2fa` | Skips 2FA on next login | ~90 days |

On each run, the Firebase token is refreshed automatically. If the `verified2fa` token is still valid, no 2FA prompt is needed.

## File Structure

```
playmetrics-export/
├── playmetrics_export.py       # Main export script
├── requirements.txt            # Python dependencies
├── .env.example                # Credential template
├── .env                        # Your credentials (not committed)
├── .gitignore                  # Git ignore rules
├── README.md                   # This file
└── playmetrics_players_*.csv   # Exported data (not committed)
```

## Troubleshooting

### "Missing dependencies" error
```bash
pip install -r requirements.txt
```

### Login fails with "INVALID_LOGIN_CREDENTIALS"
- Verify your email and password in `.env`
- Make sure your PlayMetrics account is active

### 2FA code not arriving
- Check your phone for SMS from PlayMetrics
- Wait a minute and try running the script again

### "Invalid access_key" error
The saved access key has expired. Delete the auth file and re-authenticate:
```bash
# Windows
del "%LOCALAPPDATA%\playmetrics_auth.json"

# Then run again - it will prompt for 2FA
python playmetrics_export.py
```

### Reset everything
To start completely fresh:
```bash
# Windows
del "%LOCALAPPDATA%\playmetrics_auth.json"

# Mac/Linux
rm ~/.local/playmetrics_auth.json
```

## Security Notes

- Your password is stored in `.env` which is excluded from git via `.gitignore`
- Auth tokens in `playmetrics_auth.json` grant access to your account - keep the file private
- Exported CSV files contain personal information (names, emails, phone numbers) - handle appropriately
- Never commit `.env`, `playmetrics_auth.json`, or `*.csv` files to version control

## License

MIT License - feel free to modify and use as needed.

## Contributing

Issues and pull requests are welcome on GitHub.
