import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from curl_cffi import requests
from datetime import datetime

GAMERPOWER_API_FILTER = "https://www.gamerpower.com/api/filter"
PLATFORMS = ["steam", "epic-games-store", "gog", "ubisoft"]

ALLOWED_PLATFORMS = [
    "(Steam) Giveaway",
    "(Epic Games) Giveaway",
    "(GOG) Giveaway",
    "(Ubisoft) Giveaway"
]

EXCLUDED_KEYWORDS = [
    "starter pack",
    "content pack",
    "starter kit",
    "dlc pack",
    "cosmetic pack",
    "bonus pack",
    "dlc",
    "expansion pack",
    "season pass",
    "add-on",
    "addon",
    "in-game item",
    "in-game content",
    "cosmetic",
    "skin pack",
    "bundle pack",
    "character pack",
    "weapon pack",
    "loot pack"
]

def resolve_redirect(url):
    if not url:
        return None
    try:
        response = requests.get(url, allow_redirects=True, timeout=8, impersonate="chrome110")
        return response.url
    except:
        return url

def clean_game_name(title):
    for platform_str in ALLOWED_PLATFORMS:
        title = title.replace(platform_str, "").strip()
    return title

def is_valid_giveaway(title, description=""):
    if not any(platform in title for platform in ALLOWED_PLATFORMS):
        return False
    
    title_lower = title.lower()
    desc_lower = (description or "").lower()
    
    for keyword in EXCLUDED_KEYWORDS:
        if keyword in title_lower or keyword in desc_lower:
            return False
    
    dlc_patterns = [
        " dlc ",
        "dlc:",
        "- dlc",
        "(dlc)",
        "downloadable content",
        "expansion:",
        "chapter pack",
        "booster pack"
    ]
    
    for pattern in dlc_patterns:
        if pattern in title_lower or pattern in desc_lower:
            return False
    
    return True

def extract_platform_from_title(title):
    if "(Steam)" in title:
        return "steam"
    elif "(Epic Games)" in title:
        return "epic-games-store"
    elif "(GOG)" in title:
        return "gog"
    elif "(Ubisoft)" in title:
        return "ubisoft"
    return None

def process_game(game, idx, total):
    game_title = game.get('title', '')
    game_desc = game.get('description', '')
    
    if not is_valid_giveaway(game_title, game_desc):
        reason = "Not a valid giveaway or DLC/pack detected"
        return None, f"[{idx}/{total}] SKIPPED: {game_title} ({reason})"
    
    platform = extract_platform_from_title(game_title)
    clean_name = clean_game_name(game_title)
    
    giveaway_url = game.get('open_giveaway_url') or game.get('giveaway_url')
    final_url = resolve_redirect(giveaway_url) if giveaway_url else None
    
    worth = game.get('worth', 'Free')
    if worth == 'N/A' or worth.lower() == 'free':
        price = "Free"
    else:
        worth_clean = worth.replace('$', '').strip()
        price = f"${worth_clean} → Free"
    
    game_info = {
        'name': clean_name,
        'description': game.get('description'),
        'price': price,
        'post_date': game.get('published_date'),
        'link': final_url,
        'platform': platform
    }
    
    return game_info, f"[{idx}/{total}] ✓ {clean_name} ({platform})"

def fetch_gamerpower_games():
    all_games = []
    
    try:
        platform_string = ".".join(PLATFORMS)
        api_url = f"{GAMERPOWER_API_FILTER}?platform={platform_string}&type=game.loot&sort-by=date"
        
        print(f"\nFetching games from GamerPower API...")
        
        response = requests.get(api_url, timeout=15, impersonate="chrome110")
        response.raise_for_status()
        games = response.json()
        
        if not games or (isinstance(games, dict) and games.get('status_code') == 201):
            print("  No active giveaways found")
            return all_games
        
        if isinstance(games, dict):
            games = [games]
        
        total = len(games)
        print(f"  Found {total} game(s) from API")
        print("-" * 60)
        
        # Process games in parallel but maintain order
        with ThreadPoolExecutor(max_workers=10) as executor:
            # Submit all tasks with their index
            future_to_index = {
                executor.submit(process_game, game, idx, total): idx 
                for idx, game in enumerate(games, 1)
            }
            
            # Collect results with their indices
            results = {}
            for future in as_completed(future_to_index):
                idx = future_to_index[future]
                result, message = future.result()
                results[idx] = (result, message)
            
            # Print and add games in original order
            for idx in sorted(results.keys()):
                result, message = results[idx]
                print(message)
                if result:
                    all_games.append(result)
        
        print(f"\n" + "-" * 60)
        print(f"Total collected: {len(all_games)} games")
        
    except Exception as e:
        print(f"  Error: {e}")
    
    return all_games

def save_to_json(games, filename='games.gpAPI.json'):
    platforms_used = sorted(set(g['platform'] for g in games if g['platform']))
    
    data = {
        'last_updated': datetime.now().isoformat(),
        'total_games': len(games),
        'platforms': platforms_used,
        'games': games
    }
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"\n✓ Saved {len(games)} games to {filename}")

def main():
    print("\n" + "=" * 60)
    print("Fetching Free Games from GamerPower API")
    print("=" * 60)
    
    games = fetch_gamerpower_games()
    
    if games:
        save_to_json(games, 'games.gpAPI.json')
        print("\n✓ Scraping complete!")
    else:
        print("\n✗ No games found")
    
    print("=" * 60)

if __name__ == "__main__":
    main()