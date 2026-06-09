import requests
import json
import os

# ==================== CONFIGURATION ====================
COOKIE_FILE = "roblosecurity.txt"
# =======================================================

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json;charset=UTF-8"
}

def load_roblox_cookie(file_path):
    """Reads the .ROBLOSECURITY token from a text file."""
    if not os.path.exists(file_path):
        print(f"[-] Error: '{file_path}' not found in this folder.")
        print("[*] Please create the file and paste your .ROBLOSECURITY token inside it.")
        return None
        
    with open(file_path, "r", encoding="utf-8") as f:
        cookie_data = f.read().strip()
        
    if not cookie_data:
        print(f"[-] Error: '{file_path}' is empty.")
        return None
        
    return cookie_data

def get_user_id(username):
    """Resolves a username to a Roblox User ID."""
    url = "https://users.roblox.com/v1/usernames/users"
    payload = {
        "usernames": [username],
        "excludeBannedUsers": True
    }
    
    try:
        response = requests.post(url, headers=HEADERS, json=payload)
        response_data = response.json()
        if "data" in response_data and len(response_data["data"]) > 0:
            return response_data["data"][0]["id"]
        else:
            print(f"[-] User '{username}' not found or is banned.")
            return None
    except Exception as e:
        print(f"[-] Error getting User ID: {e}")
        return None

def check_profile_presence(user_id, cookies):
    """Checks if the user is in a game and extracts universeId."""
    url = "https://apis.roblox.com/profile-platform-api/v1/profiles/get"
    payload = {
        "profileId": str(user_id),
        "profileType": "User",
        "components": [
            {"component": "CurrentlyPlaying"}
        ],
        "includeComponentOrdering": True
    }
    
    try:
        response = requests.post(url, headers=HEADERS, cookies=cookies, json=payload)
        res_json = response.json()
        
        components = res_json.get("components", {})
        currently_playing = components.get("CurrentlyPlaying", {})
        
        if currently_playing.get("isInExperience") and "universeId" in currently_playing:
            return currently_playing["universeId"]
        return None
    except Exception as e:
        print(f"[-] Error checking profile presence: {e}")
        return None

def find_server_match(universe_id, user_id, cookies):
    """Scans friend server instances to find the matching player ID."""
    url = f"https://games.roblox.com/v1/games/{universe_id}/servers/Friend"
    
    try:
        response = requests.get(url, headers=HEADERS, cookies=cookies)
        res_json = response.json()
        
        server_list = res_json.get("data", [])
        if not server_list:
            return None
            
        for server in server_list:
            for player in server.get("players", []):
                if player.get("id") == user_id:
                    return {
                        "serverId": server.get("id"),
                        "playing": server.get("playing"),
                        "maxPlayers": server.get("maxPlayers")
                    }
        return None
    except Exception as e:
        print(f"[-] Error fetching friend servers endpoint: {e}")
        return None

def main():
    # Load cookie configuration at launch
    cookie_token = load_roblox_cookie(COOKIE_FILE)
    if not cookie_token:
        return
        
    cookies = {".ROBLOSECURITY": cookie_token}
    
    target_username = input("Enter the Roblox username to track: ").strip()
    if not target_username:
        return
    
    print(f"[*] Resolving User ID for {target_username}...")
    user_id = get_user_id(target_username)
    if not user_id:
        return

    print(f"[*] Checking presence details for User ID: {user_id}...")
    universe_id = check_profile_presence(user_id, cookies)
    
    if not universe_id:
        print(f"[-] {target_username} is not currently in a game (or status is private).")
        return
        
    print(f"[+] User is active in Universe ID: {universe_id}. Scanning active server nodes...")
    server_details = find_server_match(universe_id, user_id, cookies)
    
    if server_details:
        server_id = server_details["serverId"]
        players_count = f"{server_details['playing']}/{server_details['maxPlayers']}"
        
        print("\n" + "="*50)
        print(f"SERVER ID: {server_id}")
        print(f"JOIN URL: roblox://experiences/start?placeId={universe_id}&gameInstanceId={server_id}")
        print(f"PLAYERS IN SERVER: {players_count}")
        print("="*50 + "\n")
    else:
        print(f"[-] Could not track the exact server instance. Status may be unjoinable or hidden.")

if __name__ == "__main__":
    main()