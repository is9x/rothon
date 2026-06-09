import requests
import time
import json

MAX_RETRIES = 6

def log_response(r):
    print("\n" + "=" * 80)
    print(f"{r.request.method} {r.request.url}")
    print("-" * 80)

    print("REQUEST HEADERS:")
    for k, v in r.request.headers.items():
        print(f"{k}: {v}")

    body = r.request.body

    if body:
        print("\nREQUEST BODY:")
        try:
            print(body.decode() if isinstance(body, bytes) else body)
        except:
            print(body)

    print("\n" + "-" * 80)
    print(f"STATUS: {r.status_code}")

    print("\nRESPONSE BODY:")

    try:
        print(json.dumps(r.json(), indent=4))
    except:
        print(r.text)

    print("=" * 80 + "\n")

def save_cookie(cookie):
    with open("altcookie.txt", "w", encoding="utf-8") as f:
        f.write(cookie)

def create_session(cookie):
    s = requests.Session()

    s.cookies[".ROBLOSECURITY"] = cookie

    s.headers.update({
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://www.roblox.com"
    })

    return s

def get_csrf(session):
    r = session.post(
        "https://accountsettings.roblox.com/v1/email"
    )

    log_response(r)

    token = r.headers.get("x-csrf-token")

    if token:
        session.headers["x-csrf-token"] = token
        print(f"[+] CSRF TOKEN: {token}")
    else:
        raise Exception("Failed to obtain CSRF token")

def get_authenticated_user(session):
    r = session.get(
        "https://users.roblox.com/v1/users/authenticated"
    )

    log_response(r)

    r.raise_for_status()

    data = r.json()

    return data["id"], data["name"]

def check_are_friends(session, user1, user2):
    url = f"https://friends.roblox.com/v1/users/{user1}/friends/{user2}"

    r = session.get(url)

    log_response(r)

    return r.status_code == 200

def fetch_friendship_date(session, user1, user2):
    url = "https://apis.roblox.com/profile-insights-api/v1/multiProfileInsights"

    payload = {
        "rankingStrategy": "tc_info_boost",
        "userIds": [user1, user2]
    }

    delay = 10.0

    for attempt in range(MAX_RETRIES + 1):
        try:
            print(f"\n[+] ATTEMPT {attempt + 1}/{MAX_RETRIES + 1}")

            r = session.post(url, json=payload)

            log_response(r)

            r.raise_for_status()

            data = r.json()

            for entry in data.get("userInsights", []):
                for insight in entry.get("profileInsights", []):
                    friendship = insight.get("friendshipAgeInsight")

                    if friendship:
                        ts = friendship["friendsSinceDateTime"]

                        unix = (
                            ts["seconds"] +
                            ts["nanos"] / 1_000_000_000
                        )

                        return time.strftime(
                            "%Y-%m-%d %H:%M:%S",
                            time.localtime(unix)
                        )

            print("[!] No friendshipAgeInsight returned")

        except Exception as e:
            print(f"[!] ERROR: {e}")

        print(f"[!] Sleeping {delay}s...")
        time.sleep(delay)

        delay = min(delay * 2, 60)

    return None

def main():
    cookie = input("Enter Roblosecurity: ").strip()

    if cookie.startswith(".ROBLOSECURITY="):
        cookie = cookie.split("=", 1)[1]

    save_cookie(cookie)

    print("[+] Cookie saved to altcookie.txt")

    session = create_session(cookie)

    get_csrf(session)

    auth_id, auth_name = get_authenticated_user(session)

    print("\n[+] Authenticated User")
    print(f"Username: {auth_name}")
    print(f"UserID: {auth_id}")

    print("\nNote: user1 must have friended user2")

    user1 = int(input("Enter the first userID: ").strip())
    user2 = int(input("Enter the second userID: ").strip())

    print("\n[+] Checking direct friendship endpoint...")

    are_friends = check_are_friends(
        session,
        user1,
        user2
    )

    if are_friends:
        print("[+] user1 IS friends with user2")
    else:
        print("[+] user1 is NOT friends with user2")

    print("\n[+] Fetching friendship insight date...")

    date = fetch_friendship_date(
        session,
        user1,
        user2
    )

    if date:
        print(f"\nDate they added eachother: {date}")
    else:
        print("\nFailed to fetch friendship date")

if __name__ == "__main__":
    main()