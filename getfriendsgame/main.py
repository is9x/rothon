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

YELLOW = "\033[93m"
RESET = "\033[0m"

ASCII_ART = YELLOW + "\n" + "\n".join([
    "        __     ____     _                __                                         ",
    "   ____ ____  / /_   / __/____(_)__  ____  ____/ /____   ____ _____ _____ ___  ___ ",
    "  / __ `/ _ \\/ __/  / /_/ ___/ / _ \\/ __ \\/ __  / ___/  / __ `/ __ `/ __ `__ \\/ _ \\",
    " / /_/ /  __/ /_   / __/ /  / /  __/ / / / /_/ (__  )  / /_/ / /_/ / / / / / /  __/",
    " \\__, /\\___/\\__/  /_/ /_/  /_/\\___/_/ /_/\\__,_/____/   \\__, /\\__,_/_/ /_/ /_/\\___/ ",
    "/____/                                                /____/                        "
]) + RESET

def print_logo():
    print(ASCII_ART)

def load_or_prompt_cookie(file_path):
    cookie_data = ""
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            cookie_data = f.read().strip()
    if not cookie_data:
        cookie_data = input("Enter your ROBLOSECURITY cookie: ").strip()
        if not cookie_data:
            print("[-] Error: No cookie provided. Exiting.")
            return None
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(cookie_data)
        print(f"[+] Saved cookie to {file_path} for future use.")
    return cookie_data

def get_user_id(username):
    url = "https://users.roblox.com/v1/usernames/users"
    payload = {"usernames": [username], "excludeBannedUsers": True}
    try:
        response = requests.post(url, headers=HEADERS, json=payload)
        response_data = response.json()
        if "data" in response_data and len(response_data["data"]) > 0:
            return response_data["data"][0]["id"]
        print(f"[-] User '{username}' not found or is banned.")
        return None
    except Exception as e:
        print(f"[-] Error getting User ID: {e}")
        return None

def check_via_presence(user_id, cookies):
    url = "https://presence.roblox.com/v1/presence/users"
    payload = {"userIds": [int(user_id)]}
    try:
        response = requests.post(url, headers=HEADERS, cookies=cookies, json=payload)
        res_json = response.json()
        presences = res_json.get("userPresences", [])
        if not presences:
            return None
        presence = presences[0]
        p_type = presence.get("userPresenceType", 0)
        if p_type == 0:
            print(f"[-] User is currently offline.")
            return "offline"
        elif p_type == 1:
            print(f"[-] User is online, but not in a game.")
            return "online"
        elif p_type == 2:
            return {
                "placeId": presence.get("placeId"),
                "gameId": presence.get("gameId"),
                "gameName": presence.get("lastLocation", "Unknown Game")
            }
    except Exception as e:
        pass
    return None

def get_server_details(place_id, game_instance_id, cookies):
    url = f"https://games.roblox.com/v1/games/{place_id}/servers/Friend"
    try:
        response = requests.get(url, headers=HEADERS, cookies=cookies)
        res_json = response.json()
        servers = res_json.get("data", [])
        for server in servers:
            if server.get("id") == game_instance_id:
                return server.get("playing")
    except Exception as e:
        pass
    return "Unknown"

def check_profile_fallback(user_id, cookies):
    url = "https://apis.roblox.com/profile-platform-api/v1/profiles/get"
    payload = {
        "profileId": str(user_id),
        "profileType": "User",
        "components": [{"component": "CurrentlyPlaying"}],
        "includeComponentOrdering": True
    }
    try:
        response = requests.post(url, headers=HEADERS, cookies=cookies, json=payload)
        res_json = response.json()
        components = res_json.get("components", {})
        currently_playing = components.get("CurrentlyPlaying", {})
        if currently_playing.get("isInExperience") and "universeId" in currently_playing:
            return currently_playing["universeId"]
    except Exception as e:
        pass
    return None

def get_server_details_by_universe(universe_id, user_id, cookies):
    url = f"https://games.roblox.com/v1/games/{universe_id}/servers/Friend"
    try:
        response = requests.get(url, headers=HEADERS, cookies=cookies)
        res_json = response.json()
        servers = res_json.get("data", [])
        for server in servers:
            for player in server.get("players", []):
                if player.get("id") == user_id:
                    return {"serverId": server.get("id"), "playing": server.get("playing")}
    except Exception as e:
        pass
    return None

def main():
    print_logo()
    cookie_token = load_or_prompt_cookie(COOKIE_FILE)
    if not cookie_token:
        return
    cookies = {".ROBLOSECURITY": cookie_token}
    target_username = input("Enter the Roblox username to track: ").strip()
    if not target_username:
        return
    
    print(f"[*] Calling User ID for {target_username}...")
    user_id = get_user_id(target_username)
    if not user_id:
        return

    print(f"[*] Calling presence details...")
    presence_data = check_via_presence(user_id, cookies)
    if presence_data in ["offline", "online"]:
        return
        
    if isinstance(presence_data, dict):
        place_id = presence_data["placeId"]
        game_instance_id = presence_data["gameId"]
        game_name = presence_data["gameName"]
        print(f"[*] Calling server details...")
        player_count = get_server_details(place_id, game_instance_id, cookies)
        print("\n" + "="*50)
        print(f"GAME NAME: {game_name}")
        print(f"PLAYERS IN SERVER: {player_count}")
        print(f"SERVER ID: {game_instance_id}")
        print(f"JOIN URL: roblox://experiences/start?placeId={place_id}&gameInstanceId={game_instance_id}")
        print("="*50 + "\n")
        return

    universe_id = check_profile_fallback(user_id, cookies)
    if not universe_id:
        print(f"[-] {target_username} is not currently in a game (or profile visibility settings are fully private).")
        return
        
    print(f"[*] Calling server details...")
    fallback_details = get_server_details_by_universe(universe_id, user_id, cookies)
    if fallback_details:
        server_id = fallback_details["serverId"]
        player_count = fallback_details["playing"]
        print("\n" + "="*50)
        print(f"GAME NAME: (Fetched via Fallback Universe: {universe_id})")
        print(f"PLAYERS IN SERVER: {player_count}")
        print(f"SERVER ID: {server_id}")
        print(f"JOIN URL: roblox://experiences/start?placeId={universe_id}&gameInstanceId={server_id}")
        print("="*50 + "\n")
    else:
        print(f"[-] Target is in an unjoinable instance, private server, or an untrackable sub-place branch.")

if __name__ == "__main__":
    main()