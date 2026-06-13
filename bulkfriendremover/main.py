"""
Roblox Friend Remover (Profile Insights version)
-----------------------------------------------
Removes Roblox friends based on the actual friendship date returned by
https://apis.roblox.com/profile-insights-api/v1/multiProfileInsights

Usage:
    python real.py
    python real.py -debug

Configuration is done via prompts at runtime, or by setting the
ROBLOSECURITY environment variable for the cookie.
"""

import os
import sys
import time
import json
from datetime import datetime, timezone, timedelta

import requests

MAX_RETRIES = 6
DEBUG_MODE = ("-debug" in sys.argv)

USERS_API = "https://users.roblox.com"
FRIENDS_API = "https://friends.roblox.com"
PROFILE_INSIGHTS_API = "https://apis.roblox.com/profile-insights-api/v1/multiProfileInsights"


# ---------------------------------------------------------------------------
# Debug logging
# ---------------------------------------------------------------------------

def log_response(r: requests.Response) -> None:
    if not DEBUG_MODE:
        return

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
        except Exception:
            print(body)

    print("\n" + "-" * 80)
    print(f"STATUS: {r.status_code}")

    print("\nRESPONSE BODY:")
    try:
        print(json.dumps(r.json(), indent=4))
    except Exception:
        print(r.text)

    print("=" * 80 + "\n")


# ---------------------------------------------------------------------------
# Session / auth helpers
# ---------------------------------------------------------------------------

def create_session(cookie: str) -> requests.Session:
    s = requests.Session()
    s.cookies[".ROBLOSECURITY"] = cookie
    s.headers.update({
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://www.roblox.com",
        "Accept": "application/json, text/plain, */*",
    })
    return s


def get_csrf(session: requests.Session) -> None:
    r = session.post("https://accountsettings.roblox.com/v1/email")
    log_response(r)
    token = r.headers.get("x-csrf-token")
    if not token:
        raise RuntimeError("Failed to obtain CSRF token")
    session.headers["x-csrf-token"] = token


def get_authenticated_user(session: requests.Session) -> dict:
    url = f"{USERS_API}/v1/users/authenticated"
    r = session.get(url)
    log_response(r)
    r.raise_for_status()
    return r.json()


def get_friends(session: requests.Session, user_id: int) -> list[dict]:
    url = f"{FRIENDS_API}/v1/users/{user_id}/friends"
    r = session.get(url)
    log_response(r)
    r.raise_for_status()
    return r.json().get("data", [])


def are_friends(session: requests.Session, my_user_id: int, target_user_id: int) -> bool:
    url = f"{FRIENDS_API}/v1/users/{my_user_id}/friends/statuses"
    r = session.get(url, params={"userIds": target_user_id})
    log_response(r)
    r.raise_for_status()
    data = r.json().get("data", [])
    return bool(data and data[0].get("status") == "Friends")


def unfriend(session: requests.Session, target_user_id: int) -> None:
    url = f"{FRIENDS_API}/v1/users/{target_user_id}/unfriend"
    r = session.post(url)
    log_response(r)
    if r.status_code == 403 and "x-csrf-token" in r.headers:
        session.headers["x-csrf-token"] = r.headers["x-csrf-token"]
        r = session.post(url)
        log_response(r)
    r.raise_for_status()


# ---------------------------------------------------------------------------
# Profile Insights: friendship date
# ---------------------------------------------------------------------------

def fetch_friendship_datetime(session: requests.Session, my_id: int, friend_id: int) -> datetime | None:
    payload = {
        "rankingStrategy": "tc_info_boost",
        "userIds": [my_id, friend_id],
    }

    delay = 10.0

    for attempt in range(MAX_RETRIES + 1):
        try:
            if DEBUG_MODE:
                print(f"\n[DEBUG] Friendship insight attempt {attempt + 1}/{MAX_RETRIES + 1} for {friend_id}")

            r = session.post(PROFILE_INSIGHTS_API, json=payload)
            log_response(r)
            r.raise_for_status()

            data = r.json()

            for entry in data.get("userInsights", []):
                for insight in entry.get("profileInsights", []):
                    friendship = insight.get("friendshipAgeInsight")
                    if not friendship:
                        continue
                    ts = friendship.get("friendsSinceDateTime")
                    if not ts:
                        continue

                    seconds = ts.get("seconds")
                    nanos = ts.get("nanos", 0)

                    if seconds is None:
                        continue

                    unix = seconds + nanos / 1_000_000_000
                    return datetime.fromtimestamp(unix, tz=timezone.utc)

        except Exception:
            pass

        if attempt < MAX_RETRIES:
            time.sleep(delay)
            delay = min(delay * 2, 60)

    return None


# ---------------------------------------------------------------------------
# Date parsing helper
# ---------------------------------------------------------------------------

def parse_iso(dt_str: str) -> datetime:
    dt_str = dt_str.rstrip("Z").split(".")[0]
    return datetime.fromisoformat(dt_str).replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Main logic
# ---------------------------------------------------------------------------

def main() -> None:
    cookie = os.environ.get("ROBLOSECURITY", "").strip()
    if not cookie:
        cookie = input("Enter your .ROBLOSECURITY cookie value: ").strip()

    if cookie.startswith(".ROBLOSECURITY="):
        cookie = cookie.split("=", 1)[1]

    if not cookie:
        print("Error: .ROBLOSECURITY cookie is required.", file=sys.stderr)
        sys.exit(1)

    session = create_session(cookie)
    get_csrf(session)

    print("\nAuthenticating …")
    me = get_authenticated_user(session)
    my_id = me["id"]
    print(f"Logged in as: {me['name']} (ID: {my_id})")

    print("\nSelect a time range for friends you want to remove.")
    print("  1) Last hour")
    print("  2) Last 2 hours")
    print("  3) Last day")
    print("  4) Last week")
    print("  5) Custom (enter your own range)")
    choice = input("Choice: ").strip()

    now_utc = datetime.now(timezone.utc)

    if choice == "1":
        start_dt = now_utc - timedelta(hours=1)
        end_dt = now_utc
    elif choice == "2":
        start_dt = now_utc - timedelta(hours=2)
        end_dt = now_utc
    elif choice == "3":
        start_dt = now_utc - timedelta(days=1)
        end_dt = now_utc
    elif choice == "4":
        start_dt = now_utc - timedelta(weeks=1)
        end_dt = now_utc
    else:
        print("\nEnter the date/time range for friends you want to remove.")
        print("Examples:")
        print("  2026-06-13")
        print("  2026-06-13T03:40:00")
        print("  2026-06-13T03:40:00Z\n")

        start_str = input("Start (inclusive, UTC): ").strip()
        end_str = input("End   (inclusive, UTC): ").strip()

        start_dt = parse_iso(start_str)
        end_dt = parse_iso(end_str)

        if len(end_str) == 10:
            end_dt = end_dt.replace(hour=23, minute=59, second=59)

    if end_dt < start_dt:
        print("Error: end date must not be before start date.", file=sys.stderr)
        sys.exit(1)

    delay_input = input("Delay between unfriend requests in seconds [default: 1]: ").strip()
    try:
        unfriend_delay = float(delay_input) if delay_input else 1.0
    except ValueError:
        unfriend_delay = 1.0

    dry_run = input("Dry run? (y/N): ").strip().lower() in ("y", "yes")

    print("\nFetching friends list …")
    friends = get_friends(session, my_id)
    print(f"Total friends: {len(friends)}")

    print("\nResolving friendship dates via Profile Insights API …")
    candidates = []

    for idx, friend in enumerate(friends, start=1):
        fid = friend["id"]
        fname = friend.get("name", "")
        print(f"[{idx}/{len(friends)}] {fname} (ID {fid}) …", end=" ")

        dt = fetch_friendship_datetime(session, my_id, fid)
        if not dt:
            print("no date.")
            time.sleep(0.05)
            continue

        print(f"friends since {dt.isoformat()}")

        if start_dt <= dt <= end_dt:
            friend["_friends_since"] = dt
            candidates.append(friend)

        time.sleep(0.05)

    print(
        f"\nFriends added between {start_dt} and {end_dt}: "
        f"{len(candidates)}"
    )

    if not candidates:
        print("No friends match the given date range. Nothing to do.")
        return

    if dry_run:
        print("\n[Dry run] The following friends would be removed:")
        for f in candidates:
            dt = f.get("_friends_since")
            print(f"  • {f.get('name', '')} (ID: {f['id']}, friends since: {dt})")
        return

    confirm = input(
        f"\nAbout to remove {len(candidates)} friend(s). Continue? (y/N): "
    ).strip().lower()
    if confirm not in ("y", "yes"):
        print("Aborted.")
        return

    removed = 0
    skipped = 0
    errors = 0

    for idx, friend in enumerate(candidates, start=1):
        fid = friend["id"]
        fname = friend.get("name", "")
        prefix = f"[{idx}/{len(candidates)}]"

        print(f"{prefix} Checking friendship status with {fname} (ID: {fid}) …", end=" ")
        try:
            if not are_friends(session, my_id, fid):
                print("not friends — skipping.")
                skipped += 1
                time.sleep(unfriend_delay)
                continue
        except Exception as exc:
            print(f"error: {exc} — skipping.")
            errors += 1
            time.sleep(unfriend_delay)
            continue

        print("confirmed friends.")

        print(f"{prefix} Removing {fname} (ID: {fid}) …", end=" ")
        try:
            unfriend(session, fid)
            print("done.")
            removed += 1
        except Exception as exc:
            print(f"error: {exc}")
            errors += 1

        time.sleep(unfriend_delay)

    print(
        f"\nFinished. Removed: {removed} | Skipped (not friends): {skipped} | "
        f"Errors: {errors}"
    )


if __name__ == "__main__":
    main()
