# Roblox Friend Remover (Profile Insights Edition)
### RFR v2.0 — by is9x

This tool removes Roblox friends based on the **actual friendship timestamp** returned by the Profile Insights API.  
Unlike the deprecated Friends API, this method provides the real date you added each friend.

## Features
- Fetches real friendship timestamps via:
  `https://apis.roblox.com/profile-insights-api/v1/multiProfileInsights`
- Supports time‑range filtering:
  - Last hour  
  - Last 2 hours  
  - Last day  
  - Last week  
  - Custom UTC range  
- Fast timestamp resolution (0.05s per friend)
- User‑controlled delay for unfriending
- Dry‑run mode
- Debug mode (`-debug`) to print raw API requests/responses

## Requirements
- Python 3.9+
- `pip install requests`
- Your `.ROBLOSECURITY` cookie

## Usage

### Run normally:
`python main.py`

### Run with debug logging:
`python main.py -debug`

### Optional environment variable:
`set ROBLOSECURITY=_|WARNING:...`

## How It Works
1. Authenticates using your `.ROBLOSECURITY` cookie  
2. Retrieves your friend list  
3. For each friend, calls the Profile Insights API to obtain:
   - `friendsSinceDateTime.seconds`
   - `friendsSinceDateTime.nanos`
4. Converts the timestamp to UTC  
5. Filters friends based on your selected time window  
6. Unfriends them with your chosen delay  

## Notes
- Friendship timestamps are accurate to the millisecond  
- Roblox rate‑limits unfriending; use a reasonable delay  
- Timestamp fetching is lightweight and fixed at 0.05s per friend  

## License
GNU General Public License
