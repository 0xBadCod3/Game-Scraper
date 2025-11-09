import json
import re
import time
from curl_cffi import requests
from bs4 import BeautifulSoup
from datetime import datetime
import html

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

def get_platform(link):
    """Determine platform from link"""
    if not link:
        return None
    
    link_lower = link.lower()
    if 'steam' in link_lower:
        return 'steam'
    elif 'epicgames' in link_lower:
        return 'epic-games-store'
    elif 'gog' in link_lower:
        return 'gog'
    elif 'ubisoft' in link_lower:
        return 'ubisoft'
    return None

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
        
        # Determine platform
        game_info['platform'] = get_platform(game_info['link'])
        
        # Filter: only keep if platform is valid
        if not game_info['platform']:
            print(f"Skipped (no valid platform): {game_info['name']}")
            continue
        
        games.append(game_info)
        print(f"Found: {game_info['name']} [{game_info['platform']}]")
    
    return games

def scrape_with_pagination(base_url, num_pages=5):
    """Scrape multiple pages"""
    all_games = []
    url = base_url
    
    for page_num in range(num_pages):
        print(f"\n--- Page {page_num + 1}/{num_pages} ---")
        
        html_content = fetch_telegram_page(url)
        if not html_content:
            break
        
        soup = BeautifulSoup(html_content, 'html.parser')
        games = extract_games(soup)
        all_games.extend(games)
        
        # Get oldest message ID for pagination
        messages = soup.find_all('div', class_='tgme_widget_message', attrs={'data-post': True})
        if not messages:
            print("No more messages")
            break
        
        url = f"{base_url}?before={messages[0]['data-post'].split('/')[-1]}"
        time.sleep(1.5)
    
    return all_games

def save_to_json(games, filename='games.tg.json'):
    """Save games to JSON file"""
    # Sort by date
    games.sort(key=lambda x: x.get('post_date') or '', reverse=True)
    
    data = {
        'last_updated': datetime.now().isoformat(),
        'total_games': len(games),
        'games': games
    }
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"\nSaved {len(games)} games to {filename}")

def main():
    print("Starting scrape...")
    games = scrape_with_pagination("https://t.me/s/freegames", num_pages=20)
    
    if games:
        save_to_json(games, 'games.tg.json')
    else:
        print("\nNo games found")

if __name__ == "__main__":
    main()