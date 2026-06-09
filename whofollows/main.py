import requests
import json
import os
import sys
import time
import pyperclip  # pip install pyperclip

# ==================== CONFIGURATION ====================
COOKIE_FILE = "roblosecurity.txt"
OUTPUT_FILE = "followersusernames.txt"
# =======================================================

# ANSI Escape codes for formatting
BLUE = "\033[94m"
RESET = "\033[0m"

ASCII_ART = BLUE + "\n" + "\n".join([
    r"        .__                _____      .__  .__                      ",
    r"__  _  _ |  |__   ____   _/ ____\____ |  | |  |    ______  _  ______",
    r"\ \/ \/ /|  |  \ /  _ \  \   __\/  _ \|  | |  |   /  _ \ \/ \/ /  ___/",
    r" \     / |   Y  (  <_> )  |  | (  <_> )  |_|  |__(  <_> )     /\___ \ ",
    r"  \/\_/  |___|  /\____/   |__|  \____/|____/____/\____/ \/\_//____  >",
    r"              \/                                                  \/"
]) + RESET

def print_logo():
    """Prints the custom ASCII art logo at the start of execution."""
    print(ASCII_ART)

def load_or_prompt_cookie(file_path):
    """Reads the cookie from the file, or prompts the user if empty/missing."""
    cookie_data = ""
    
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            cookie_data = f.read().strip()
            
    # Strip any leading standard browser prefixes if pasted raw
    if cookie_data.startswith(".ROBLOSECURITY="):
        cookie_data = cookie_data.split("=", 1)[1]
            
    if not cookie_data:
        cookie_data = input("Enter your ROBLOSECURITY cookie: ").strip()
        if not cookie_data:
            print("[-] Error: No cookie provided. Exiting.")
            return None
            
        if cookie_data.startswith(".ROBLOSECURITY="):
            cookie_data = cookie_data.split("=", 1)[1]
            
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(cookie_data)
        print(f"[+] Saved cookie to {file_path} for future use.")
        
    return cookie_data

def create_session(cookie_value):
    """Initializes the requests Session wrapper."""
    s = requests.Session()
    s.cookies[".ROBLOSECURITY"] = cookie_value
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.roblox.com"
    })
    return s

def get_csrf(session):
    """Fetches a valid x-csrf-token from the security gateway endpoint."""
    r = session.post("https://accountsettings.roblox.com/v1/email")
    session.headers["x-csrf-token"] = r.headers.get("x-csrf-token")

def username_to_userid(session, username):
    """Resolves a username string into a numerical Roblox target ID."""
    r = session.post(
        "https://users.roblox.com/v1/usernames/users",
        json={
            "usernames": [username],
            "excludeBannedUsers": False
        }
    )
    r.raise_for_status()
    data = r.json()["data"]

    if not data or data[0]["id"] == 0:
        print("[-] Error: Username not found.")
        sys.exit(1)

    return data[0]["id"]

def get_follower_ids(session, user_id):
    """Extracts all follower list IDs across all index result pages."""
    followers = []
    cursor = ""

    while cursor is not None:
        params = {
            "limit": 100,
            "sortOrder": "Desc"
        }
        if cursor:
            params["cursor"] = cursor

        r = session.get(
            f"https://friends.roblox.com/v1/users/{user_id}/followers",
            params=params
        )
        r.raise_for_status()
        data = r.json()

        for item in data.get("data", []):
            followers.append(item["id"])

        cursor = data.get("nextPageCursor")

    return followers

def get_profiles(session, batch):
    """Batches profile telemetry to parse string user keys quickly."""
    r = session.post(
        "https://apis.roblox.com/user-profile-api/v1/user/profiles/get-profiles",
        json={
            "userIds": batch,
            "fields": [
                "names.username",
                "names.combinedName",
                "isVerified",
                "isDeleted"
            ]
        }
    )
    r.raise_for_status()

    out = {}
    for p in r.json().get("profileDetails", []):
        uid = p["userId"]
        username = p["names"]["username"]
        out[uid] = username

    return out

def main():
    # 1. Clear terminal canvas and print the clean blue logo
    print_logo()

    if len(sys.argv) < 2:
        print(f"Usage: python {os.path.basename(__file__)} <username>")
        sys.exit(1)

    target_username = sys.argv[1]

    # 2. Authenticate or request cookie key credentials dynamically
    cookie = load_or_prompt_cookie(COOKIE_FILE)
    if not cookie:
        return
        
    session = create_session(cookie)
    get_csrf(session)

    print(f"[*] Resolving username '{target_username}'...")
    user_id = username_to_userid(session, target_username)
    print(f"[+] User ID: {user_id}")

    print("[*] Fetching follower IDs...")
    follower_ids = get_follower_ids(session, user_id)
    print(f"[+] Total followers: {len(follower_ids)}")

    usernames = []

    # Process chunks of 100 users cleanly
    for i in range(0, len(follower_ids), 100):
        batch = follower_ids[i:i+100]
        profiles = get_profiles(session, batch)

        for uid in batch:
            usernames.append(profiles.get(uid, "UnknownUser"))

        time.sleep(0.2)

    print("\nOutput options:")
    print("1 = Save to followersusernames.txt")
    print("2 = Copy to clipboard")

    choice = input("Choose: ").strip()

    if choice == "1":
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            for name in usernames:
                f.write(name + "\n")
        print(f"[+] Saved to {OUTPUT_FILE}")

    elif choice == "2":
        pyperclip.copy("\n".join(usernames))
        print("[+] Copied to clipboard.")

    else:
        print("[-] Invalid choice.")

if __name__ == "__main__":
    main()