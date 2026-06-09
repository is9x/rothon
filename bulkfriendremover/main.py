"""
Roblox Friend Remover
---------------------
Removes Roblox friends that were added during a specific date/time window.

Usage:
    python main.py

Configuration is done via prompts at runtime, or by setting the
ROBLOSECURITY environment variable for the cookie.
"""

import os
import sys
import time
from datetime import datetime, timezone

import requests

# ---------------------------------------------------------------------------
# Roblox API base URLs
# ---------------------------------------------------------------------------
USERS_API = "https://users.roblox.com"
FRIENDS_API = "https://friends.roblox.com"


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _get_session(roblosecurity: str) -> requests.Session:
    """Return an authenticated requests Session."""
    session = requests.Session()
    session.cookies.set(".ROBLOSECURITY", roblosecurity, domain=".roblox.com")
    session.headers.update({"User-Agent": "RobloxFriendRemover/1.0"})
    return session


def _request(session: requests.Session, method: str, url: str, **kwargs) -> requests.Response:
    """
    Perform an HTTP request.

    Raises a descriptive RuntimeError when the response is 429 (rate-limited),
    clearly identifying which endpoint triggered the limit.
    """
    response = session.request(method, url, **kwargs)
    if response.status_code == 429:
        raise RuntimeError(
            f"[429 Rate-Limited] Endpoint: {method.upper()} {url} — "
            "you are being rate-limited. Try again later or increase the delay."
        )
    return response


# ---------------------------------------------------------------------------
# Roblox API wrappers
# ---------------------------------------------------------------------------

def get_authenticated_user(session: requests.Session) -> dict:
    """Return the authenticated user's id, name, and displayName."""
    url = f"{USERS_API}/v1/users/authenticated"
    response = _request(session, "GET", url)
    response.raise_for_status()
    return response.json()


def get_friends(session: requests.Session, user_id: int) -> list[dict]:
    """
    Return the full friends list for *user_id*.

    Each entry contains at least: id, name, displayName, created (ISO 8601).
    """
    url = f"{FRIENDS_API}/v1/users/{user_id}/friends"
    response = _request(session, "GET", url)
    response.raise_for_status()
    return response.json().get("data", [])


def are_friends(session: requests.Session, my_user_id: int, target_user_id: int) -> bool:
    """
    Return True when the authenticated user is currently friends with *target_user_id*.

    Uses the /v1/users/{userId}/friends/statuses endpoint so that we don't
    waste an unfriend request on someone who is not actually a friend.
    """
    url = f"{FRIENDS_API}/v1/users/{my_user_id}/friends/statuses"
    response = _request(session, "GET", url, params={"userIds": target_user_id})
    response.raise_for_status()
    entries = response.json().get("data", [])
    if not entries:
        return False
    # status is "Friends" when actually friended
    return entries[0].get("status") == "Friends"


def unfriend(session: requests.Session, target_user_id: int) -> None:
    """Unfriend *target_user_id*."""
    url = f"{FRIENDS_API}/v1/users/{target_user_id}/unfriend"
    # The unfriend endpoint requires a CSRF token sent as X-CSRF-TOKEN.
    # Obtain the token by attempting the request; Roblox returns 403 with the
    # token in the X-CSRF-TOKEN response header on the first attempt.
    response = session.post(url)
    if response.status_code == 429:
        raise RuntimeError(
            f"[429 Rate-Limited] Endpoint: POST {url} — "
            "you are being rate-limited. Try again later or increase the delay."
        )
    if response.status_code == 403 and "X-CSRF-TOKEN" in response.headers:
        session.headers["X-CSRF-TOKEN"] = response.headers["X-CSRF-TOKEN"]
        response = _request(session, "POST", url)
    response.raise_for_status()


# ---------------------------------------------------------------------------
# Date parsing helper
# ---------------------------------------------------------------------------

def parse_iso(dt_str: str) -> datetime:
    """Parse an ISO 8601 datetime string into an aware UTC datetime."""
    # Python <3.11 doesn't support the trailing 'Z' natively in fromisoformat
    dt_str = dt_str.rstrip("Z").split(".")[0]
    return datetime.fromisoformat(dt_str).replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Main logic
# ---------------------------------------------------------------------------

def main() -> None:
    # ---- credentials -------------------------------------------------------
    roblosecurity = os.environ.get("ROBLOSECURITY", "").strip()
    if not roblosecurity:
        roblosecurity = input("Enter your .ROBLOSECURITY cookie value: ").strip()
    if not roblosecurity:
        print("Error: .ROBLOSECURITY cookie is required.", file=sys.stderr)
        sys.exit(1)

    # ---- date range --------------------------------------------------------
    print("\nEnter the date range for friends you want to remove.")
    print("Format: YYYY-MM-DD  (times are interpreted as UTC)")

    start_str = input("Start date (inclusive): ").strip()
    end_str = input("End date   (inclusive): ").strip()

    try:
        start_dt = datetime.fromisoformat(start_str).replace(tzinfo=timezone.utc)
        # Make end_dt end-of-day so that the user's date is fully inclusive
        end_dt = datetime.fromisoformat(end_str).replace(
            hour=23, minute=59, second=59, tzinfo=timezone.utc
        )
    except ValueError as exc:
        print(f"Error parsing dates: {exc}", file=sys.stderr)
        sys.exit(1)

    if end_dt < start_dt:
        print("Error: end date must not be before start date.", file=sys.stderr)
        sys.exit(1)

    # ---- delay between requests --------------------------------------------
    delay_input = input("Delay between unfriend requests in seconds [default: 1]: ").strip()
    try:
        delay = float(delay_input) if delay_input else 1.0
    except ValueError:
        delay = 1.0

    # ---- dry-run mode ------------------------------------------------------
    dry_run_input = input("Dry run? (y/N): ").strip().lower()
    dry_run = dry_run_input in ("y", "yes")

    # ---- set up session ----------------------------------------------------
    session = _get_session(roblosecurity)

    print("\nAuthenticating …")
    try:
        me = get_authenticated_user(session)
    except RuntimeError as exc:
        print(f"\n{exc}", file=sys.stderr)
        sys.exit(1)
    except requests.HTTPError as exc:
        print(f"Authentication failed: {exc}", file=sys.stderr)
        sys.exit(1)

    my_user_id: int = me["id"]
    print(f"Logged in as: {me['name']} (ID: {my_user_id})")

    # ---- fetch friends -----------------------------------------------------
    print("\nFetching friends list …")
    try:
        friends = get_friends(session, my_user_id)
    except RuntimeError as exc:
        print(f"\n{exc}", file=sys.stderr)
        sys.exit(1)

    print(f"Total friends: {len(friends)}")

    # ---- filter by date range ----------------------------------------------
    candidates = []
    for friend in friends:
        created_str = friend.get("created", "")
        if not created_str:
            continue
        try:
            created_dt = parse_iso(created_str)
        except ValueError:
            continue
        if start_dt <= created_dt <= end_dt:
            candidates.append(friend)

    print(
        f"Friends added between {start_dt.date()} and {end_dt.date()}: "
        f"{len(candidates)}"
    )

    if not candidates:
        print("No friends match the given date range. Nothing to do.")
        return

    if dry_run:
        print("\n[Dry run] The following friends would be removed:")
        for f in candidates:
            print(f"  • {f['name']} (ID: {f['id']}, added: {f.get('created', 'unknown')})")
        return

    # ---- confirm -----------------------------------------------------------
    confirm = input(
        f"\nAbout to remove {len(candidates)} friend(s). Continue? (y/N): "
    ).strip().lower()
    if confirm not in ("y", "yes"):
        print("Aborted.")
        return

    # ---- unfriend ----------------------------------------------------------
    removed = 0
    skipped = 0
    errors = 0

    for idx, friend in enumerate(candidates, start=1):
        fid: int = friend["id"]
        fname: str = friend["name"]
        prefix = f"[{idx}/{len(candidates)}]"

        # -- friendship check ------------------------------------------------
        print(f"{prefix} Checking friendship status with {fname} (ID: {fid}) …", end=" ")
        try:
            is_friend = are_friends(session, my_user_id, fid)
        except RuntimeError as exc:
            # 429 on the status-check endpoint — log it and skip
            print(f"\n{exc}")
            errors += 1
            time.sleep(delay)
            continue
        except requests.HTTPError as exc:
            print(f"HTTP error: {exc} — skipping.")
            errors += 1
            time.sleep(delay)
            continue

        if not is_friend:
            print(f"not friends — skipping.")
            skipped += 1
            time.sleep(delay)
            continue

        print("confirmed friends.")

        # -- unfriend --------------------------------------------------------
        print(f"{prefix} Removing {fname} (ID: {fid}) …", end=" ")
        try:
            unfriend(session, fid)
            print("done.")
            removed += 1
        except RuntimeError as exc:
            # 429 on the unfriend endpoint — log the exact endpoint URL
            print(f"\n{exc}")
            errors += 1
        except requests.HTTPError as exc:
            print(f"HTTP error: {exc}")
            errors += 1

        time.sleep(delay)

    # ---- summary -----------------------------------------------------------
    print(
        f"\nFinished. Removed: {removed} | Skipped (not friends): {skipped} | "
        f"Errors: {errors}"
    )


if __name__ == "__main__":
    main()
