import json
import unicodedata
import re
from datetime import datetime
from scraper_tg import scrape_with_pagination
from scraper_gp_api import fetch_gamerpower_games
from scraper_gp_web import scrape_gamerpower

def normalize_name(name):
    if not name:
        return ""
    normalized = unicodedata.normalize('NFKD', name)
    normalized = normalized.encode('ascii', 'ignore').decode('ascii')
    normalized = normalized.lower()
    normalized = re.sub(r'[^\w\s]', '', normalized)
    normalized = re.sub(r'\s+', ' ', normalized)
    return normalized.strip()

def merge_game_entries(game1, game2):
    merged = game1.copy()
    for key in game2:
        if key not in merged or merged[key] is None:
            merged[key] = game2[key]
    return merged

def find_insertion_position(ordered_games, new_game, source_games):
    norm_new = normalize_name(new_game.get('name', ''))
    
    new_game_index_in_source = None
    for idx, game in enumerate(source_games):
        if normalize_name(game.get('name', '')) == norm_new:
            new_game_index_in_source = idx
            break
    
    if new_game_index_in_source is None:
        return len(ordered_games)
    
    game_before = None
    game_after = None
    
    for i in range(new_game_index_in_source - 1, -1, -1):
        norm = normalize_name(source_games[i].get('name', ''))
        if any(normalize_name(g.get('name', '')) == norm for g in ordered_games):
            game_before = norm
            break
    
    for i in range(new_game_index_in_source + 1, len(source_games)):
        norm = normalize_name(source_games[i].get('name', ''))
        if any(normalize_name(g.get('name', '')) == norm for g in ordered_games):
            game_after = norm
            break
    
    if game_after:
        for idx, game in enumerate(ordered_games):
            if normalize_name(game.get('name', '')) == game_after:
                return idx
    
    if game_before:
        for idx, game in enumerate(ordered_games):
            if normalize_name(game.get('name', '')) == game_before:
                return idx + 1
    
    return len(ordered_games)

def merge_ordered_games(base_games, new_source_games, source_name):
    print(f"\nMerging {source_name}...")
    
    norm_to_game = {normalize_name(g.get('name', '')): i for i, g in enumerate(base_games)}
    result = base_games.copy()
    
    for game in new_source_games:
        norm_name = normalize_name(game.get('name', ''))
        if not norm_name:
            continue
        
        if norm_name in norm_to_game:
            idx = norm_to_game[norm_name]
            result[idx] = merge_game_entries(result[idx], game)
            print(f"  ↔ Updated: {game.get('name', 'Unknown')}")
        else:
            insert_pos = find_insertion_position(result, game, new_source_games)
            result.insert(insert_pos, game.copy())
            
            for norm, idx in norm_to_game.items():
                if idx >= insert_pos:
                    norm_to_game[norm] = idx + 1
            norm_to_game[norm_name] = insert_pos
            
            print(f"  + Added at position {insert_pos}: {game.get('name', 'Unknown')}")
    
    return result

def save_merged_json(games, filename='games.json'):
    platforms = sorted(list(set(g.get('platform') for g in games if g.get('platform'))))
    
    data = {
        'last_updated': datetime.now().isoformat(),
        'total_games': len(games),
        'platforms': platforms,
        'games': games
    }
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"\n{'='*60}")
    print(f"✓ Saved {len(games)} games to {filename}")
    print(f"Platforms: {', '.join(platforms)}")
    print('='*60)

def main():
    print("\n" + "="*60)
    print("GAME SCRAPER MERGER")
    print("="*60)
    
    print("\n[1/3] Running scraper3 (GamerPower Web)...")
    scraper3_games, scraper3_platforms = scrape_gamerpower(num_pages=2, max_workers=3)
    if scraper3_games is None:
        scraper3_games = []
    
    print("\n[2/3] Running scraper1 (Telegram)...")
    scraper1_games = scrape_with_pagination("https://t.me/s/freegames", num_pages=10)
    
    print("\n[3/3] Running scraper2 (GamerPower API)...")
    scraper2_games = fetch_gamerpower_games()
    
    print("\n" + "="*60)
    print("MERGING PROCESS")
    print("="*60)
    
    try:
        with open('games.json', 'r', encoding='utf-8') as f:
            existing_merged = json.load(f).get('games', [])
    except:
        existing_merged = []
    
    merged = scraper3_games
    merged = merge_ordered_games(merged, scraper1_games, "scraper1")
    merged = merge_ordered_games(merged, scraper2_games, "scraper2")
    
    if len(merged) > len(existing_merged):
        save_merged_json(merged, 'games.json')
        print("\n✓ Merge complete!")
    else:
        print("\n✓ No new games found. JSON not updated.")

if __name__ == "__main__":
    main()