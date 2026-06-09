import requests
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

# ==================== CONFIGURATION ====================
COOKIE_FILE = "roblosecurity.txt"
DEBUG_MODE = True  # Set to False to hide the verbose API tracking
# =======================================================

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "Origin": "https://www.roblox.com",
    "Referer": "https://www.roblox.com/"
}

BLUE = "\033[94m"
YELLOW = "\033[93m"
GREEN = "\033[92m"
RESET = "\033[0m"

def print_logo():
    print(f"{BLUE}Who The Hell Is That by is9x{RESET}\n")

def debug(msg):
    if DEBUG_MODE:
        print(f"{YELLOW}[DEBUG]{RESET} {msg}")

def load_or_prompt_cookie(file_path):
    cookie_data = ""
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            cookie_data = f.read().strip()
    if cookie_data.startswith(".ROBLOSECURITY="):
        cookie_data = cookie_data.split("=", 1)[1]
    if not cookie_data:
        cookie_data = input("Enter your ROBLOSECURITY cookie: ").strip()
        if not cookie_data:
            print("[-] Error: No cookie provided. Exiting.")
            sys.exit(1)
        if cookie_data.startswith(".ROBLOSECURITY="):
            cookie_data = cookie_data.split("=", 1)[1]
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(cookie_data)
        print(f"[+] Saved cookie to {file_path} for future use.")
    return cookie_data

def get_csrf(session):
    r = session.post("https://accountsettings.roblox.com/v1/email")
    session.headers["x-csrf-token"] = r.headers.get("x-csrf-token")
    debug(f"CSRF Token grabbed: {session.headers.get('x-csrf-token')}")

def username_to_userid(session, username):
    url = "https://users.roblox.com/v1/usernames/users"
    r = session.post(url, json={"usernames": [username], "excludeBannedUsers": False})
    
    if r.status_code != 200:
        print(f"[-] API Error (Status {r.status_code}). Roblox says: {r.text}")
        sys.exit(1)
        
    data = r.json().get("data", [])
    if data:
        debug(f"Resolved {username} -> UID: {data[0]['id']}")
        return data[0]["id"]
    print(f"[-] Username '{username}' not found.")
    sys.exit(1)

def extract_hash(image_url):
    try:
        return image_url.split("AvatarHeadshot-")[1].split("-")[0]
    except:
        return None

def get_user_headshot_hash(session, user_id):
    url = f"https://thumbnails.roblox.com/v1/users/avatar-headshot?userIds={user_id}&size=150x150&format=Webp&isCircular=false"
    r = session.get(url)
    data = r.json().get("data", [])
    if data and data[0].get("imageUrl"):
        h = extract_hash(data[0]["imageUrl"])
        debug(f"Target Headshot Hash: {h}")
        return h
    debug(f"Failed to get headshot for {user_id}. Response: {r.text}")
    return None

def get_presence_place_id(session, user_id):
    url = "https://presence.roblox.com/v1/presence/users"
    r = session.post(url, json={"userIds": [int(user_id)]})
    presences = r.json().get("userPresences", [])
    if presences:
        p = presences[0]
        if p.get("userPresenceType") == 2:
            debug(f"Target is in game. PlaceId: {p.get('placeId')}")
            return p.get("placeId")
    debug(f"Target is not in-game or privacy prevents tracking. Response: {r.text}")
    return None

def get_tokens_from_friend_servers(session, place_id):
    url = f"https://games.roblox.com/v1/games/{place_id}/servers/Friend?limit=100"
    r = session.get(url)
    data = r.json().get("data", [])
    servers = []
    for s in data:
        servers.append({
            "id": s.get("id"),
            "playing": s.get("playing", 0),
            "tokens": s.get("playerTokens", [])
        })
    debug(f"Found {len(servers)} servers in /Friend endpoint.")
    return servers

def batch_resolve_tokens(session, tokens):
    if not tokens:
        return []
    url = "https://thumbnails.roblox.com/v1/batch"
    payload = []
    for t in tokens:
        payload.append({
            "format": "Webp",
            "type": "AvatarHeadShot",
            "token": t,
            "size": "150x150",
            "requestId": f"AvatarHeadShot::{t}::150x150:Webp:"
        })
    r = session.post(url, json=payload)
    results = r.json().get("data", [])
    hashes = []
    for res in results:
        img_url = res.get("imageUrl", "")
        if img_url:
            h = extract_hash(img_url)
            if h: hashes.append(h)
    return hashes

def get_all_friends(session, user_id):
    url = f"https://friends.roblox.com/v1/users/{user_id}/friends"
    r = session.get(url)
    friends = r.json().get("data", [])
    debug(f"Pulled {len(friends)} friends for target.")
    return friends

def batch_resolve_friends(session, friend_list):
    friend_map = {}
    uids = [str(f["id"]) for f in friend_list]
    
    for i in range(0, len(uids), 100):
        chunk = uids[i:i+100]
        csv = ",".join(chunk)
        url = f"https://thumbnails.roblox.com/v1/users/avatar-headshot?userIds={csv}&size=150x150&format=Webp&isCircular=false"
        r = session.get(url)
        for item in r.json().get("data", []):
            if item.get("imageUrl"):
                h = extract_hash(item["imageUrl"])
                if h:
                    friend_map[h] = item["targetId"]
    debug(f"Successfully mapped {len(friend_map)} friend headshots.")
    return friend_map

def get_username(session, user_id):
    url = f"https://users.roblox.com/v1/users/{user_id}"
    r = session.get(url)
    return r.json().get("name", "Unknown")

def get_friendship_date(session, target_uid, match_uid):
    url = "https://apis.roblox.com/profile-insights-api/v1/multiProfileInsights?_rosealRequest="
    payload = {"rankingStrategy": "tc_info_boost", "userIds": [int(target_uid), int(match_uid)]}
    r = session.post(url, json=payload)
    try:
        insights = r.json().get("userInsights", [])
        for user_data in insights:
            profile_insights = user_data.get("profileInsights", [])
            for insight in profile_insights:
                if "friendshipAgeInsight" in insight:
                    seconds = insight["friendshipAgeInsight"]["friendsSinceDateTime"]["seconds"]
                    
                    dt_utc = datetime.fromtimestamp(seconds, timezone.utc)
                    dt_local = dt_utc.astimezone() 
                    
                    hour_12 = dt_local.hour % 12
                    if hour_12 == 0: hour_12 = 12
                    am_pm = dt_local.strftime('%p')
                    
                    return f"{dt_local.month}/{dt_local.day}/{dt_local.year} {hour_12}:{dt_local.minute:02d}{am_pm}"
    except Exception as e:
        debug(f"Insights parsing failed: {e} | Response: {r.text}")
    return "Unknown"

def check_joinable(session, target_uid):
    url = "https://gamejoin.roblox.com/v1/play-with-user?_rosealPlatformType=Desktop"
    payload = {
        "userIdToFollow": int(target_uid), 
        "joinOrigin": "RoSealFetchInfo", 
        "gameJoinAttemptId": "0db0833c-ab24-42c5-8a79-51f3aa2a935b"
    }
    r = session.post(url, json=payload)
    res_data = r.json()
    debug(f"Joinable response: {json.dumps(res_data)}")
    
    if res_data.get("jobId") or res_data.get("joinScriptUrl"):
        return "Yes"
    return "No"

def main():
    print_logo()
    
    if len(sys.argv) >= 2:
        target_username = sys.argv[1]
    else:
        target_username = input("Enter your friend's username: ").strip()
        if not target_username:
            print("[-] Error: No username provided. Exiting.")
            sys.exit(1)
        
    cookie = load_or_prompt_cookie(COOKIE_FILE)
    
    session = requests.Session()
    session.cookies[".ROBLOSECURITY"] = cookie
    session.headers.update(HEADERS)
    
    print("[*] Init authentication & tokens...")
    get_csrf(session)
    
    print(f"[*] Resolving target '{target_username}'...")
    target_uid = username_to_userid(session, target_username)
    target_hash = get_user_headshot_hash(session, target_uid)
    
    print("[*] Fetching target PlaceId...")
    place_id = get_presence_place_id(session, target_uid)
    
    if not place_id:
        print("[-] Could not isolate PlaceId. Target is either offline or privacy settings block Presence.")
        return

    print("[*] Scanning servers via getfriendsgame endpoint...")
    servers = get_tokens_from_friend_servers(session, place_id)
    
    target_server = None
    target_server_hashes = []
    
    for s in servers:
        hashes = batch_resolve_tokens(session, s["tokens"])
        if target_hash in hashes:
            debug(f"Target hash found in server {s['id']}")
            target_server = s
            target_server_hashes = hashes
            break

    total_people = 0
    match_username = "Unknown/Not in Friend List"
    friendship_date = "Unknown"
    
    if target_server:
        total_people = target_server["playing"]
        mystery_hashes = [h for h in target_server_hashes if h != target_hash]
        debug(f"Mystery hashes to identify: {mystery_hashes}")
        
        if mystery_hashes:
            print("[*] Fetching and mapping entire friend roster headshots...")
            friends = get_all_friends(session, target_uid)
            friend_map = batch_resolve_friends(session, friends)
            
            matched_uids = []
            for mh in mystery_hashes:
                if mh in friend_map:
                    matched_uids.append(friend_map[mh])
            
            debug(f"Matched UIDs: {matched_uids}")
            
            if matched_uids:
                match_uid = matched_uids[0]
                print("[*] Pulling profile insights for identified match...")
                match_username = get_username(session, match_uid)
                friendship_date = get_friendship_date(session, target_uid, match_uid)
    else:
        debug("Could not locate the specific server block containing target's token.")

    print("[*] Probing gamejoin access protocols...")
    joinable_status = check_joinable(session, target_uid)
    
    print(f"\n{GREEN}==========================")
    print(f"AMOUNT OF PEOPLE IN PRIVATE SERVER: {total_people}")
    print(f"PLAYER YOUR FRIEND IS WITH: {match_username}")
    print(f"DATE THEY BECAME FRIENDS: {friendship_date}")
    print(f"IS SERVER JOINABLE: {joinable_status}")
    print(f"=========================={RESET}")

if __name__ == "__main__":
    main()