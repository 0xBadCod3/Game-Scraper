import json
import re
import time
from curl_cffi import requests
from bs4 import BeautifulSoup
from datetime import datetime
import html
import os

def fetch_telegram_page(url):
    """Fetch the Telegram page using curl_cffi"""
    try:
        response = requests.get(url, impersonate="chrome110", timeout=10)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"Error fetching page: {e}")
        return None

def parse_game_info(text):
    """Parse game information from message text"""
    if not re.search(r'\[(?:Windows|Win)\]', text, re.IGNORECASE):
        return None
    
    # Extract game name
    name_match = re.search(r'\[(?:Windows|Win)\]\s*\[(.*?)\]', text, re.IGNORECASE)
    if not name_match:
        return None
    
    game_name = html.unescape(name_match.group(1).strip())
    
    # Extract price (currency symbol + arrow)
    price_match = re.search(r'\[([^\]]*?(?:\$|€|£|₹)[^\]]*?(?:→|->)[^\]]*?)\]', text)
    price = html.unescape(price_match.group(1).strip()) if price_match else None
    
    # Extract description (longest bracket, excluding platform/name/price)
    all_brackets = re.findall(r'\[(.*?)\]', text)
    description = None
    
    for bracket in reversed(all_brackets):
        if (len(bracket) > 20 and 
            not re.search(r'(?:Windows|Win)', bracket, re.IGNORECASE) and 
            bracket != game_name and 
            not re.search(r'(?:\$|€|£|₹)[^\]]*?(?:→|->)', bracket)):
            description = html.unescape(bracket.strip())
            break
    
    return {'name': game_name, 'description': description, 'price': price}

def extract_games(soup):
    """Extract game information from parsed HTML"""
    games = []
    
    for container in soup.find_all('div', class_='tgme_widget_message'):
        message = container.find('div', class_='tgme_widget_message_text')
        if not message:
            continue
        
        game_info = parse_game_info(message.get_text(separator=' ', strip=True))
        if not game_info:
            continue
        
        # Extract post date
        time_element = container.find('time', datetime=True)
        game_info['post_date'] = time_element['datetime'] if time_element else None
        
        # Extract game link (skip telegram links)
        game_info['link'] = next(
            (link['href'] for link in container.find_all('a', href=True) 
             if 't.me' not in link['href'] and link['href'].startswith('http')),
            None
        )
        
        games.append(game_info)
        print(f"Found: {game_info['name']}")
    
    return games

def load_existing_games(filename='games.tg.json'):
    """Load existing games from JSON file"""
    if not os.path.exists(filename):
        return []
    
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f).get('games', [])
    except (json.JSONDecodeError, IOError) as e:
        print(f"Error loading existing file: {e}")
        return []

def scrape_with_pagination(base_url, num_pages=5, existing_games=None):
    """Scrape multiple pages, stop at already seen games"""
    all_games = []
    existing_ids = {(g['name'], g['link']) for g in existing_games or [] if g.get('name') and g.get('link')}
    url = base_url
    
    for page_num in range(num_pages):
        print(f"\n--- Page {page_num + 1}/{num_pages} ---")
        
        html_content = fetch_telegram_page(url)
        if not html_content:
            break
        
        soup = BeautifulSoup(html_content, 'html.parser')
        games = extract_games(soup)
        
        # Check if we've reached already scraped games
        for game in games:
            if (game['name'], game['link']) in existing_ids:
                print(f"Already have: {game['name']} - stopping pagination")
                return all_games
            all_games.append(game)
        
        # Get oldest message ID for pagination
        messages = soup.find_all('div', class_='tgme_widget_message', attrs={'data-post': True})
        if not messages:
            print("No more messages")
            break
        
        url = f"{base_url}?before={messages[0]['data-post'].split('/')[-1]}"
        time.sleep(1.5)
    
    return all_games

def merge_and_sort_games(new_games, existing_games):
    """Merge new games with existing ones and sort by date"""
    all_games_dict = {(g.get('name'), g.get('link')): g for g in existing_games}
    
    for game in new_games:
        game_id = (game.get('name'), game.get('link'))
        if game_id not in all_games_dict:
            all_games_dict[game_id] = game
    
    unique_games = list(all_games_dict.values())
    unique_games.sort(key=lambda x: x.get('post_date') or '', reverse=True)
    
    return unique_games

def save_to_json(games, filename='games.tg.json'):
    """Save games to JSON file"""
    data = {
        'last_updated': datetime.now().isoformat(),
        'total_games': len(games),
        'games': games
    }
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"\nSaved {len(games)} total games to {filename}")

def main():
    filename = 'games.tg.json'
    
    print("Loading existing games...")
    existing_games = load_existing_games(filename)
    print(f"Found {len(existing_games)} existing games")
    
    print("\nStarting scrape...")
    new_games = scrape_with_pagination("https://t.me/s/freegames", num_pages=5, existing_games=existing_games)
    
    if new_games:
        print(f"\nFound {len(new_games)} new games")
        all_games = merge_and_sort_games(new_games, existing_games)
        save_to_json(all_games, filename)
    elif existing_games:
        print("\nNo new games found, keeping existing data")
    else:
        print("\nNo games found")

if __name__ == "__main__":
    main()