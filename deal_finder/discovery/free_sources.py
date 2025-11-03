"""Free, reliable news sources that actually work."""

import logging
from datetime import datetime
from typing import List
from xml.etree import ElementTree as ET

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class RSSFeedReader:
    """Read RSS/Atom feeds from press release sites."""

    def __init__(self, timeout: int = 20):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })

    def fetch_rss(self, url: str) -> List[dict]:
        """Fetch and parse RSS feed."""
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()

            # Parse XML
            root = ET.fromstring(response.content)

            articles = []

            # Try RSS 2.0 format
            for item in root.findall('.//item'):
                title = item.find('title')
                link = item.find('link')
                pubDate = item.find('pubDate')
                description = item.find('description')

                if link is not None:
                    # Extract text, handling None values
                    title_text = title.text.strip() if title is not None and title.text else ''
                    desc_text = description.text.strip() if description is not None and description.text else ''

                    # Use description as title if title is empty
                    final_title = title_text if title_text else desc_text

                    articles.append({
                        'url': link.text.strip(),
                        'title': final_title,
                        'published_date': pubDate.text.strip() if pubDate is not None and pubDate.text else None,
                        'snippet': desc_text,
                        'source': 'RSS'
                    })

            # Try Atom format if no RSS items found
            if not articles:
                for entry in root.findall('.//{http://www.w3.org/2005/Atom}entry'):
                    title = entry.find('{http://www.w3.org/2005/Atom}title')
                    link = entry.find('{http://www.w3.org/2005/Atom}link')
                    updated = entry.find('{http://www.w3.org/2005/Atom}updated')
                    summary = entry.find('{http://www.w3.org/2005/Atom}summary')

                    if title is not None and link is not None:
                        articles.append({
                            'url': link.get('href', ''),
                            'title': title.text.strip() if title.text else '',
                            'published_date': updated.text.strip() if updated is not None else None,
                            'snippet': summary.text.strip() if summary is not None else '',
                            'source': 'RSS'
                        })

            logger.info(f"Fetched {len(articles)} articles from RSS feed")
            return articles

        except Exception as e:
            logger.warning(f"Failed to fetch RSS from {url}: {e}")
            return []


class GoogleNewsReader:
    """Search Google News (free, no API key needed)."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })

    def search(self, query: str, max_results: int = 50) -> List[dict]:
        """Search Google News for query."""
        try:
            # Google News RSS search (still works!)
            url = f"https://news.google.com/rss/search?q={query}+biotech+OR+pharma&hl=en-US&gl=US&ceid=US:en"

            response = self.session.get(url, timeout=20)
            response.raise_for_status()

            # Parse RSS
            root = ET.fromstring(response.content)
            articles = []

            for item in root.findall('.//item'):
                title = item.find('title')
                link = item.find('link')
                pubDate = item.find('pubDate')
                description = item.find('description')

                if title is not None and link is not None:
                    articles.append({
                        'url': link.text.strip(),
                        'title': title.text.strip() if title.text else '',
                        'published_date': pubDate.text.strip() if pubDate is not None else None,
                        'snippet': description.text.strip() if description is not None else '',
                        'source': 'Google News'
                    })

                    if len(articles) >= max_results:
                        break

            logger.info(f"Found {len(articles)} articles from Google News for '{query}'")
            return articles

        except Exception as e:
            logger.warning(f"Google News search failed: {e}")
            return []


class FreeSourceRegistry:
    """Registry of free, working news sources."""

    # Public RSS feeds (no auth required)
    RSS_FEEDS = {
        'FierceBiotech': 'https://www.fiercebiotech.com/rss/xml',
        'FiercePharma': 'https://www.fiercepharma.com/rss/xml',
        'GEN': 'https://www.genengnews.com/feed/',
        'BioPharm': 'https://www.biopharminternational.com/rss',
    }

    def __init__(self):
        self.rss_reader = RSSFeedReader()
        self.google_news = GoogleNewsReader()

    def search_all(self, query: str, max_results: int = 100) -> List[dict]:
        """Search all free sources."""
        all_articles = []
        seen_urls = set()

        # 1. RSS Feeds FIRST (more reliable, direct URLs)
        for name, feed_url in self.RSS_FEEDS.items():
            if len(all_articles) >= max_results:
                break

            articles = self.rss_reader.fetch_rss(feed_url)
            for article in articles:
                url = article['url']
                # Check if query terms appear in title or snippet
                title_lower = article.get('title', '').lower()
                snippet_lower = article.get('snippet', '').lower()
                query_terms = query.lower().split()

                # Match if any query term is in title or snippet
                if url not in seen_urls and any(term in title_lower or term in snippet_lower for term in query_terms):
                    seen_urls.add(url)
                    article['source'] = name
                    all_articles.append(article)

                    if len(all_articles) >= max_results:
                        break

        logger.info(f"Found {len(all_articles)} articles from RSS feeds")

        # 2. Skip Google News (redirect URLs don't work reliably)
        # Would need special handling to extract real URLs from Google News redirects

        logger.info(f"Total articles found: {len(all_articles)}")
        return all_articles[:max_results]
