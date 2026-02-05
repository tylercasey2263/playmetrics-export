# PlayMetrics Player Export

Exports player data with contact information from PlayMetrics to CSV.

## Features

- Automatic browser login via Selenium (no manual token copying)
- Token caching (avoids re-login for ~50 minutes)
- Auto-refresh on token expiration
- Exports player info with parent/guardian contacts

## Requirements

- Python 3.8+
- Google Chrome browser installed

## Installation

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Set up credentials:
   ```bash
   copy .env.example .env
   ```

3. Edit `.env` and add your PlayMetrics password:
   ```
   PLAYMETRICS_EMAIL=your_email@example.com
   PLAYMETRICS_PASSWORD=your_password
   ```

## Usage

```bash
python playmetrics_export.py
```

The script will:
1. Log into PlayMetrics automatically (headless Chrome)
2. Cache authentication tokens for future runs
3. Fetch all players, teams, and programs
4. Export to a timestamped CSV file (e.g., `playmetrics_players_20240215_143022.csv`)

## Output

The CSV includes:
- Player ID, First Name, Last Name
- Birth Date, Gender
- Program(s)
- Parent 1-4 Name and Email

## Troubleshooting

**"Missing dependencies" error:**
```bash
pip install -r requirements.txt
```

**Login fails or times out:**
- Verify your email/password in `.env`
- Check if PlayMetrics login page has changed
- A screenshot is saved to `login_error_screenshot.png` on failure

**Token expired errors:**
- Delete `.playmetrics_tokens.json` to force re-login
- The script should auto-refresh, but manual deletion ensures a clean state

## Files

| File | Description |
|------|-------------|
| `playmetrics_export.py` | Main export script |
| `.env` | Your credentials (not committed) |
| `.env.example` | Template for credentials |
| `.gitignore` | Excludes sensitive files from git |
| `.playmetrics_tokens.json` | Cached auth tokens (auto-generated) |
