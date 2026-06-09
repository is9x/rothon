import asyncio
import aiohttp
import itertools
import sys
import os

# --- TERMINAL COLORS ---
BLUE = "\033[94m"
YELLOW = "\033[93m"
GREEN = "\033[92m"
RED = "\033[91m"
RESET = "\033[0m"

# --- CONFIGURATION ---
COOKIE_FILE = "roblosecurity.txt"
DEBUG_MODE = False  

BASE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
    "Accept": "application/json"
}

def print_logo():
    if os.name == 'nt':
        os.system('') 
    print(f"{BLUE}Who The Hell Is That by is9x (Matrix Engine){RESET}")
    print(f"{BLUE}>> Async Public Server Hunting Engine <<{RESET}\n")

def log_debug(msg, debug_mode):
    if debug_mode:
        print(f"{YELLOW}[DEBUG]{RESET} {msg}")

def log_info(msg):
    print(f"{BLUE}[*]{RESET} {msg}")

def log_success(msg):
    print(f"{GREEN}[+]{RESET} {msg}")

def log_error(msg):
    print(f"{RED}[-]{RESET} {msg}")

def load_cookie_pool(filepath):
    try:
        with open(filepath, 'r', encoding="utf-8") as f:
            cookies = [line.strip() for line in f if line.strip() and not line.startswith("#")]
        if not cookies:
            log_error(f"{filepath} is empty. Add your .ROBLOSECURITY cookies line by line.")
            sys.exit(1)
        log_success(f"Loaded {len(cookies)} authentication cookies from {filepath}")
        return cookies
    except FileNotFoundError:
        log_error(f"Could not find '{filepath}'. Please create it in the exact same folder.")
        sys.exit(1)

class AsyncRobloxFinder:
    def __init__(self, place_id, target_username, cookies, debug_mode):
        self.place_id = place_id
        self.target_username = target_username
        self.cookie_cycler = itertools.cycle(cookies)
        self.debug_mode = debug_mode
        self.target_headshot_url = None
        self.target_user_id = None
        self.universe_id = None
        self.scan_attempt = 1
        
        # Tracking states
        self.total_active_players = 0
        self.searched_tokens_cache = set()  

    def _get_rotated_cookies(self):
        return {".ROBLOSECURITY": next(self.cookie_cycler)}

    async def fetch_target_profile(self, session):
        log_info(f"Resolving profile details for: {self.target_username}...")
        
        async with session.post(
            "https://users.roblox.com/v1/usernames/users",
            json={"usernames": [self.target_username], "excludeBannedUsers": False},
            cookies=self._get_rotated_cookies()
        ) as res:
            user_data = await res.json()
            if not user_data.get("data"):
                log_error(f"Error: Target username '{self.target_username}' not found.")
                sys.exit(1)
            self.target_user_id = user_data["data"][0]["id"]

        avatar_url = f"https://thumbnails.roblox.com/v1/users/avatar-headshot?userIds={self.target_user_id}&size=150x150&format=Png&isCircular=false"
        async with session.get(avatar_url, cookies=self._get_rotated_cookies()) as res:
            avatar_data = await res.json()
            self.target_headshot_url = avatar_data["data"][0]["imageUrl"]
            
        log_success(f"Target Verified (ID: {self.target_user_id})")

    async def fetch_game_stats(self, session):
        log_info(f"Resolving Place ID -> Universe ID...")
        
        univ_url = f"https://apis.roblox.com/universes/v1/places/{self.place_id}/universe"
        async with session.get(univ_url, cookies=self._get_rotated_cookies()) as res:
            if res.status != 200:
                log_error("Failed to resolve Universe ID. Defaulting to 1 player baseline.")
                self.total_active_players = 1
                return
            univ_data = await res.json()
            self.universe_id = univ_data.get("universeId")

        games_url = f"https://games.roblox.com/v1/games?universeIds={self.universe_id}"
        async with session.get(games_url, cookies=self._get_rotated_cookies()) as res:
            if res.status == 200:
                games_data = await res.json()
                if "data" in games_data and len(games_data["data"]) > 0:
                    game_info = games_data["data"][0]
                    self.total_active_players = game_info.get("playing", 1)
                    game_name = game_info.get("name", "Unknown Game")
                    log_success(f"Game Locked: '{game_name}' | Baseline Players: {self.total_active_players}")
                else:
                    self.total_active_players = 1
            else:
                self.total_active_players = 1

    async def collect_public_servers(self, session):
        print(f"\n{BLUE}[*]{RESET} [Attempt {self.scan_attempt}] Crawling public game instances...")
        server_map = {}
        cursor = ""

        while cursor is not None:
            url = f"https://games.roblox.com/v1/games/{self.place_id}/servers/Public?limit=100&cursor={cursor}&excludeFullGames=false"
            
            async with session.get(url, cookies=self._get_rotated_cookies()) as res:
                if res.status != 200:
                    log_error(f"Rate limit or error hit on server fetch: HTTP {res.status}")
                    await asyncio.sleep(2)
                    continue
                    
                data = await res.json()
                if "data" not in data:
                    break

                for server in data["data"]:
                    tokens = server.get("playerTokens", [])
                    if tokens:
                        server_map[server["id"]] = tokens
                        
                cursor = data.get("nextPageCursor", None)
                # TIGHTENED PAGINATION DELAY
                await asyncio.sleep(0.02) 
                
        return server_map

    async def _check_batch(self, session, chunk):
        payload = [
            {"token": item["token"], "type": "AvatarHeadshot", "size": "150x150", "format": "Png", "requestId": item["requestId"]}
            for item in chunk
        ]

        async with session.post(
            "https://thumbnails.roblox.com/v1/batch", 
            json=payload, 
            cookies=self._get_rotated_cookies()
        ) as res:
            if res.status != 200:
                return None
                
            data = await res.json()
            if "data" not in data:
                return None

            for thumb_data in data["data"]:
                if thumb_data.get("imageUrl") == self.target_headshot_url:
                    return thumb_data["requestId"]
        return None

    async def process_thumbnail_batches(self, session, server_map):
        raw_queue = [{"token": tkn, "requestId": s_id} for s_id, tokens in server_map.items() for tkn in tokens]
        
        fresh_queue = [item for item in raw_queue if item["token"] not in self.searched_tokens_cache]
        
        for item in fresh_queue:
            self.searched_tokens_cache.add(item["token"])

        print(f"{BLUE}[~]{RESET} {len(self.searched_tokens_cache)}/{self.total_active_players} unique users searched...")

        if not fresh_queue:
            return None

        chunks = [fresh_queue[i:i+100] for i in range(0, len(fresh_queue), 100)]
        tasks = [self._check_batch(session, chunk) for chunk in chunks]
        results = await asyncio.gather(*tasks)
        
        for result in results:
            if result is not None:
                return result
                
        return None

    async def execute_search_loop(self):
        connector = aiohttp.TCPConnector(limit=50) 
        async with aiohttp.ClientSession(headers=BASE_HEADERS, connector=connector) as session:
            await self.fetch_target_profile(session)
            await self.fetch_game_stats(session)
            
            while True:
                server_map = await self.collect_public_servers(session)
                if not server_map:
                    log_error("No active instances found. Retrying in 5s...")
                    await asyncio.sleep(5)
                    continue
                    
                target_server_job_id = await self.process_thumbnail_batches(session, server_map)
                
                if target_server_job_id:
                    print(f"\n{GREEN}==================================================")
                    print(f"🎯 TARGET SERVER IDENTIFIED")
                    print(f"TARGET USERNAME: {self.target_username}")
                    print(f"TARGET JOB ID:   {target_server_job_id}")
                    print(f"--------------------------------------------------")
                    print(f"DEEP LINK TO JOIN (Paste in Win+R or Browser URL):")
                    print(f"roblox://experiences/start?placeId={self.place_id}&gameInstanceId={target_server_job_id}")
                    print(f"=================================================={RESET}")
                    break
                else:
                    if len(self.searched_tokens_cache) >= self.total_active_players:
                        log_debug("Entire public pool exhausted. Monitoring for new server joins...", True)
                    
                    self.scan_attempt += 1
                    # COMPROMISE DELAY: 0.2 SECONDS
                    await asyncio.sleep(0.2)

if __name__ == "__main__":
    print_logo()

    cookies = load_cookie_pool(COOKIE_FILE)

    try:
        place_input = input(f"{YELLOW}[?] Enter the Target Place ID:{RESET} ").strip()
        place_id = int(place_input)
    except ValueError:
        log_error("Place ID must be a valid number.")
        sys.exit(1)

    username = input(f"{YELLOW}[?] Enter the Target Username:{RESET} ").strip()
    if not username:
        log_error("Username cannot be empty.")
        sys.exit(1)

    finder = AsyncRobloxFinder(place_id, username, cookies, DEBUG_MODE)
    
    try:
        asyncio.run(finder.execute_search_loop())
    except KeyboardInterrupt:
        print(f"\n{RED}[!] Search gracefully aborted by user.{RESET}")