# PlayMetrics Player Export

A Python tool to automatically export player data with parent/guardian contact information from PlayMetrics to CSV.

## Features

- **Automated browser login** - Uses Selenium to handle the login flow automatically
- **2FA support** - Prompts for verification code when required
- **Device remembering** - Persistent Chrome profile saves "Remember this device" so you only need 2FA once
- **Network traffic capture** - Extracts authentication tokens from the app's own API calls
- **Complete data export** - Fetches players, teams, and programs with all contact details

## Requirements

- Python 3.8 or higher
- Google Chrome browser installed
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

On your first run, the script will:
1. Open a headless Chrome browser
2. Navigate to PlayMetrics and log in with your credentials
3. Prompt you for a 2FA verification code (sent to your phone)
4. Check "Remember this device" automatically
5. Fetch all player data and export to CSV

### Subsequent Runs

After the first successful login, future runs will:
1. Skip 2FA (device is remembered)
2. Automatically capture authentication from the app
3. Export data directly

### Example Output

```
PlayMetrics Player Export
========================================

Launching browser...
Navigating to PlayMetrics...
Already logged in! (session restored)

Fetching data from PlayMetrics...
Loading PlayMetrics players page...
  Extracting auth headers from network traffic...
  Got headers: ['firebase-token', 'pm-access-key', 'build-version']
Fetching players...
    Got players data (1891 records)
Fetching teams...
    Got teams data
Fetching programs...
    Got programs data
Found 212 teams
Found 35 programs

Exported 1891 players to playmetrics_players_20260204_204639.csv
```

## Output Format

The exported CSV includes the following columns:

| Column | Description |
|--------|-------------|
| Player ID | Unique player identifier |
| Player First Name | Player's first name |
| Player Last Name | Player's last name |
| Birth Date | Player's date of birth |
| Gender | Player's gender |
| Program(s) | Enrolled programs (semicolon-separated) |
| Parent 1 Name | Primary contact name |
| Parent 1 Email | Primary contact email |
| Parent 2 Name | Secondary contact name |
| Parent 2 Email | Secondary contact email |
| Parent 3 Name | Third contact name |
| Parent 3 Email | Third contact email |
| Parent 4 Name | Fourth contact name |
| Parent 4 Email | Fourth contact email |

## File Structure

```
playmetrics-export/
├── playmetrics_export.py   # Main export script
├── requirements.txt        # Python dependencies
├── .env.example           # Credential template
├── .env                   # Your credentials (not committed)
├── .gitignore            # Git ignore rules
├── .chrome_profile/      # Persistent browser data (not committed)
└── README.md             # This file
```

## Troubleshooting

### "Missing dependencies" error
```bash
pip install -r requirements.txt
```

### Login fails or times out
- Verify your email and password in `.env`
- Check that PlayMetrics is accessible in your browser
- Look at `error_screenshot.png` if generated

### 2FA required every time
- Delete the `.chrome_profile` folder and run again
- Make sure to check "Remember this device" when prompted

### "Could not extract headers" error
- The app may have updated its authentication method
- Try deleting `.chrome_profile` and logging in fresh
- Check if PlayMetrics works normally in your browser

### Reset everything
To start completely fresh:
```bash
# Windows
rmdir /s /q .chrome_profile

# Mac/Linux
rm -rf .chrome_profile
```

## How It Works

1. **Browser Automation**: Uses Selenium with a headless Chrome browser to navigate PlayMetrics
2. **Session Persistence**: Stores Chrome profile data locally so the "Remember this device" setting persists
3. **Network Interception**: Captures the authentication headers (Firebase token + PM access key) from Chrome's performance logs
4. **API Calls**: Uses the captured headers to make authenticated API requests for player data
5. **Data Processing**: Combines player, team, and program data into a single CSV export

## Security Notes

- Your password is stored in `.env` which is excluded from git
- The Chrome profile in `.chrome_profile/` contains session cookies - keep it private
- Exported CSV files contain personal information - handle appropriately
- Never commit `.env`, `.chrome_profile/`, or `*.csv` files to version control

## License

MIT License - feel free to modify and use as needed.

## Contributing

Issues and pull requests are welcome on GitHub.
