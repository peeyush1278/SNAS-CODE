# web_tools.py

import urllib.request
import urllib.parse
from bs4 import BeautifulSoup
import re

def search_internet(query: str, max_results: int = 5) -> str:
    """Search DuckDuckGo HTML for a query and return top links & snippets."""
    try:
        from duckduckgo_search import DDGS
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append(f"Title: {r['title']}\nURL: {r['href']}\nSnippet: {r['body']}\n")
        
        if not results:
            return "No results found."
        return "--- Search Results ---\n\n" + "\n".join(results)
    
    except ImportError:
        # Fallback to a basic DDG HTML scraper if duckduckgo_search is not installed
        try:
            url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
            with urllib.request.urlopen(req, timeout=10) as response:
                html = response.read()
            soup = BeautifulSoup(html, 'html.parser')
            
            results = []
            for a in soup.find_all('a', class_='result__snippet', limit=max_results):
                snippet = a.get_text(strip=True)
                href = a.get('href', '')
                if href.startswith('//duckduckgo.com/l/?uddg='):
                    href = urllib.parse.unquote(href.split('uddg=')[1].split('&')[0])
                results.append(f"URL: {href}\nSnippet: {snippet}\n")
            
            if not results:
                return "No results found. (Please run: pip install duckduckgo-search for better results)"
            return "--- Search Results (Fallback Scraper) ---\n\n" + "\n".join(results)
        except Exception as e:
             return f"Error executing search query. To fix, please run: pip install duckduckgo-search\nInternal Error: {e}"

def read_website(url: str) -> str:
    """Fetch and extract text content from a webpage."""
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
        with urllib.request.urlopen(req, timeout=10) as response:
            html = response.read()
            soup = BeautifulSoup(html, 'html.parser')
            
            # Remove scripts and styles
            for script in soup(["script", "style", "nav", "footer", "header"]):
                script.extract()
                
            text = soup.get_text(separator='\n')
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = '\n'.join(chunk for chunk in chunks if chunk)
            
            # Limit returned tokens to prevent blowing up the context window
            content = text[:8000]
            if len(text) > 8000:
                content += "\n... [Content Truncated due to length constraints]"
            
            return f"--- Content of {url} ---\n{content}"
    except urllib.error.HTTPError as e:
        return f"Error: The website blocked the request (HTTP Error {e.code}). You cannot scrape this site. Please provide this DIRECT LINK to the user instead: {url}"
    except Exception as e:
        return f"Error reading website {url}: {e}. You cannot scrape this site. Provide the link {url} to the user directly."
