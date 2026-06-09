import requests
import sys
import time
import pyperclip  # pip install pyperclip

COOKIE_FILE = "roblosecurity.txt"
OUTPUT_FILE = "followersusernames.txt"


def load_cookie():
    with open(COOKIE_FILE, "r", encoding="utf-8") as f:
        raw = f.readline().strip()
    if raw.startswith(".ROBLOSECURITY="):
        return raw.split("=", 1)[1]
    return raw


def create_session(cookie_value):
    s = requests.Session()
    s.cookies[".ROBLOSECURITY"] = cookie_value
    s.headers.update({
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://www.roblox.com"
    })
    return s


def get_csrf(session):
    r = session.post("https://accountsettings.roblox.com/v1/email")
    session.headers["x-csrf-token"] = r.headers.get("x-csrf-token")


def username_to_userid(session, username):
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
        print("Username not found.")
        sys.exit(1)

    return data[0]["id"]


def get_follower_ids(session, user_id):
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
    if len(sys.argv) < 2:
        print("Usage: python whofollow.py <username>")
        sys.exit(1)

    target_username = sys.argv[1]

    cookie = load_cookie()
    session = create_session(cookie)
    get_csrf(session)

    print(f"Resolving username '{target_username}'...")
    user_id = username_to_userid(session, target_username)
    print(f"User ID: {user_id}")

    print("Fetching follower IDs...")
    follower_ids = get_follower_ids(session, user_id)
    print(f"Total followers: {len(follower_ids)}")

    usernames = []

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
        print(f"Saved to {OUTPUT_FILE}")

    elif choice == "2":
        pyperclip.copy("\n".join(usernames))
        print("Copied to clipboard.")

    else:
        print("Invalid choice.")


if __name__ == "__main__":
    main()
