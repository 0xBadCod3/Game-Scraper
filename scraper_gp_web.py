import json
import re
from datetime import datetime
from bs4 import BeautifulSoup
from curl_cffi import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

# Pre-compile regex patterns for better performance
PRICE_PATTERN = re.compile(r'\$[\d.]+')
CARD_CLASS_PATTERN = re.compile('card')

# Platform mapping as constant
PLATFORM_MAP = {
    "(Steam) Giveaway": "steam",
    "(Epic Games) Giveaway": "epic-games-store",
    "(GOG) Giveaway": "gog",
    "(Ubisoft) Giveaway": "ubisoft"
}

SEARCH_STRINGS = [
    "(Steam) Giveaway",
    "(Epic Games) Giveaway",
    "(GOG) Giveaway",
    "(Ubisoft) Giveaway"
]

def get_final_redirect_url(open_url):
    """Follow the redirect from /open/ URL to get final destination"""
    try:
        response = requests.get(open_url, impersonate="chrome110", allow_redirects=False, timeout=10)
        
        if response.status_code in [301, 302, 303, 307, 308]:
            return response.headers.get('Location', open_url)
        
        response = requests.get(open_url, impersonate="chrome110", allow_redirects=True, timeout=10)
        return response.url
    except Exception as e:
        print(f"Error getting redirect for {open_url}: {e}")
        return open_url

def extract_price_fast(card_soup):
    """Extract price information from the card - optimized"""
    try:
        price_elem = card_soup.find(string=PRICE_PATTERN)
        if price_elem:
            price_match = PRICE_PATTERN.search(price_elem)
            if price_match:
                return f"{price_match.group()} → Free"
    except Exception:
        pass
    return "Free"

def process_single_game(text_node, matched_string, seen_urls):
    """Process a single game entry - returns game data or None"""
    parent = text_node.parent
    
    # Verify the parent has class "card-title"
    if not parent or 'card-title' not in parent.get('class', []):
        return None
    
    # Find the link
    link_tag = parent if parent.name == 'a' else parent.find_parent('a')
    
    if not link_tag or not link_tag.has_attr('href'):
        return None
    
    original_link = link_tag['href']
    
    # Ensure it's a full URL
    if not original_link.startswith('http'):
        original_link = f"https://www.gamerpower.com{original_link}"
    
    # Skip duplicates
    if original_link in seen_urls:
        return None
    
    seen_urls.add(original_link)
    
    # Extract SOMETHING from the URL
    link_parts = original_link.split('/')
    if len(link_parts) < 4:
        return None
    
    something = link_parts[-1] if link_parts[-1] else link_parts[-2]
    open_url = f"https://www.gamerpower.com/open/{something}"
    
    # Get the full text content
    text_content = parent.get_text(strip=True)
    
    print(f"\nFound: {text_content}")
    print(f"  Original link: {original_link}")
    print(f"  Open link: {open_url}")
    
    # Get the final redirect URL
    final_url = get_final_redirect_url(open_url)
    print(f"  Final link: {final_url}")
    
    # Extract game name
    game_name = text_content.replace(matched_string, "").strip()
    
    # Get platform
    platform = PLATFORM_MAP.get(matched_string, "unknown")
    
    # Find card and extract price
    card = parent.find_parent('div', class_=CARD_CLASS_PATTERN)
    price = extract_price_fast(card) if card else "Free"
    
    print(f"  Added to list")
    
    return {
        "name": game_name,
        "description": None,
        "price": price,
        "post_date": None,
        "link": final_url,
        "platform": platform
    }

def scrape_page(page_num):
    """Scrape a single page - returns list of games"""
    url = f"https://www.gamerpower.com/all/free-games?sort_by=date&page={page_num}"
    
    print(f"\n{'='*60}")
    print(f"Fetching page {page_num}...")
    print(f"URL: {url}")
    print('='*60)
    
    try:
        response = requests.get(url, impersonate="chrome110", timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        games = []
        seen_urls = set()
        
        # Get all text nodes in one go
        all_text_nodes = soup.find_all(string=True)
        
        for text_node in all_text_nodes:
            # Check if any search string is in this text node
            for search_string in SEARCH_STRINGS:
                if search_string in text_node:
                    game_data = process_single_game(text_node, search_string, seen_urls)
                    if game_data:
                        games.append(game_data)
                    break  # Only match first search string found
        
        return games
    
    except Exception as e:
        print(f"Error scraping page {page_num}: {e}")
        return []

def scrape_gamerpower(num_pages=3, max_workers=3):
    """Main scraping function with parallel page fetching
    
    Args:
        num_pages: Number of pages to scrape (starting from page 1)
        max_workers: Number of parallel workers for page fetching
    """
    
    games = []
    platforms_found = set()
    
    try:
        # Parallel page fetching
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all page scraping tasks
            future_to_page = {
                executor.submit(scrape_page, page_num): page_num 
                for page_num in range(1, num_pages + 1)
            }
            
            # Collect results as they complete
            for future in as_completed(future_to_page):
                page_games = future.result()
                
                # Add games and collect platforms
                for game in page_games:
                    games.append(game)
                    platforms_found.add(game['platform'])
        
        print(f"\n{'='*60}")
        print(f"Successfully scraped {len(games)} games!")
        print('='*60)
        
        return games, platforms_found
        
    except Exception as e:
        print(f"Error during scraping: {e}")
        return None, None

if __name__ == "__main__":
    # Change the number here to scrape more or fewer pages
    # Pages start from 1 (there is no page 0)
    num_pages = 2  # Scrape pages 1 and 2
    
    # Adjust max_workers based on your needs (2-5 is usually good)
    games, platforms_found = scrape_gamerpower(num_pages=num_pages, max_workers=3)
    
    if games is not None:
        # Create final JSON structure
        result = {
            "last_updated": datetime.now().isoformat(),
            "total_games": len(games),
            "platforms": sorted(list(platforms_found)),
            "games": games
        }
        
        # Save to JSON file
        with open('games.gpWEB.json', 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        print(f"Data saved to games.gpWEB.json")
        print('='*60)