"""URL index for tracking crawled articles."""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Set

logger = logging.getLogger(__name__)


class URLIndex:
    """Track which URLs have been crawled to enable incremental updates."""

    def __init__(self, index_path: Optional[Path] = None):
        """Initialize URL index.

        Args:
            index_path: Path to index file. Defaults to output/url_index.json
        """
        if index_path is None:
            index_path = Path("output/url_index.json")

        self.index_path = index_path
        self.crawled_urls: Set[str] = set()
        self.url_metadata: dict[str, dict] = {}
        self.load()

    def load(self):
        """Load index from disk."""
        if self.index_path.exists():
            try:
                with open(self.index_path, 'r') as f:
                    data = json.load(f)
                    self.crawled_urls = set(data.get('crawled_urls', []))
                    self.url_metadata = data.get('url_metadata', {})
                logger.info(f"Loaded URL index: {len(self.crawled_urls)} URLs already crawled")
            except Exception as e:
                logger.error(f"Failed to load URL index: {e}")
                self.crawled_urls = set()
                self.url_metadata = {}
        else:
            logger.info("No existing URL index found, starting fresh")
            self.crawled_urls = set()
            self.url_metadata = {}

    def save(self):
        """Save index to disk."""
        self.index_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(self.index_path, 'w') as f:
                json.dump({
                    'crawled_urls': list(self.crawled_urls),
                    'url_metadata': self.url_metadata,
                    'last_updated': datetime.utcnow().isoformat()
                }, f, indent=2)
            logger.info(f"Saved URL index: {len(self.crawled_urls)} URLs")
        except Exception as e:
            logger.error(f"Failed to save URL index: {e}")

    def is_crawled(self, url: str) -> bool:
        """Check if URL has been crawled.

        Args:
            url: Article URL

        Returns:
            True if already crawled
        """
        return url in self.crawled_urls

    def mark_crawled(self, url: str, metadata: Optional[dict] = None):
        """Mark URL as crawled.

        Args:
            url: Article URL
            metadata: Optional metadata (source, date, etc.)
        """
        self.crawled_urls.add(url)

        if metadata:
            self.url_metadata[url] = {
                **metadata,
                'crawled_at': datetime.utcnow().isoformat()
            }

    def mark_batch_crawled(self, urls: list[str], source: str = 'unknown'):
        """Mark multiple URLs as crawled.

        Args:
            urls: List of article URLs
            source: Source name (e.g., 'FierceBiotech')
        """
        for url in urls:
            self.mark_crawled(url, {'source': source})

    def get_new_urls(self, all_urls: list[str]) -> list[str]:
        """Filter list to only new URLs.

        Args:
            all_urls: List of all URLs from sitemap/archive

        Returns:
            List of URLs not yet crawled
        """
        new_urls = [url for url in all_urls if url not in self.crawled_urls]
        logger.info(f"Found {len(new_urls)} new URLs out of {len(all_urls)} total")
        return new_urls

    def get_stats(self) -> dict:
        """Get index statistics.

        Returns:
            Dict with stats
        """
        sources = {}
        for url_meta in self.url_metadata.values():
            source = url_meta.get('source', 'unknown')
            sources[source] = sources.get(source, 0) + 1

        return {
            'total_urls_crawled': len(self.crawled_urls),
            'by_source': sources,
            'index_path': str(self.index_path)
        }

    def get_all_urls_with_metadata(self) -> list[dict]:
        """Get all URLs from index with metadata.

        Returns:
            List of article metadata dicts with url, source, published_date
        """
        articles = []
        for url in self.crawled_urls:
            meta = self.url_metadata.get(url, {})
            articles.append({
                "url": url,
                "source": meta.get("source", "Unknown"),
                "published_date": meta.get("published_date", ""),
                "title": ""  # Title not stored in index
            })
        logger.info(f"Loaded {len(articles)} URLs from index")
        return articles

    def reset(self):
        """Reset index (for fresh crawl)."""
        self.crawled_urls = set()
        self.url_metadata = {}
        logger.warning("URL index reset - will recrawl all articles")
