"""Deal crawler for discovering press releases."""

import logging
import os
from datetime import datetime
from typing import List, Optional

from bs4 import BeautifulSoup

from ..config_loader import Config
from ..perplexity_client import PerplexityClient
from ..utils.web import WebClient
from .api_sources import APISourceRegistry
from .exhaustive_crawler import ExhaustiveSiteCrawler
from .free_sources import FreeSourceRegistry
from .sources import Source, SourceRegistry

logger = logging.getLogger(__name__)


class DealCrawler:
    """Crawl news sources for deal announcements."""

    def __init__(self, config: Config, web_client: WebClient):
        self.config = config
        self.web_client = web_client
        self.source_registry = SourceRegistry()
        self.api_registry = APISourceRegistry()
        self.free_registry = FreeSourceRegistry()

        # Priority: Exhaustive Site Crawl > Perplexity Search > Paid APIs > Free sources
        self.use_exhaustive = os.getenv("USE_EXHAUSTIVE_CRAWL", "true").lower() == "true"
        self.perplexity_key = os.getenv("PERPLEXITY_API_KEY")

        if self.use_exhaustive:
            logger.info("Using EXHAUSTIVE site crawling (recommended for complete datasets)")
            self.exhaustive_crawler = ExhaustiveSiteCrawler(
                from_date=config.START_DATE,
                to_date=config.end_date_resolved,
                use_index=True  # Enable incremental crawling by default
            )
        else:
            self.exhaustive_crawler = None

        if self.perplexity_key:
            self.perplexity_client = PerplexityClient(self.perplexity_key)
            logger.info("Perplexity API available for extraction")
        else:
            self.perplexity_client = None
            logger.warning("No Perplexity API key - will use fallback extraction")

        self.use_apis = self.api_registry.is_enabled()
        if self.use_apis:
            logger.info("Paid API sources available as fallback")

    def build_search_queries(self, ta_vocab: dict) -> List[str]:
        """Build search queries from TA vocabulary."""
        queries = []

        ta_name = ta_vocab.get("therapeutic_area", "biotech")
        ta_includes = ta_vocab.get("includes", [])

        # For Perplexity: use specific TA terms for max breadth
        if self.use_perplexity:
            deal_terms = [
                "acquisition",
                "merger",
                "partnership",
                "collaboration",
                "licensing deal",
                "option agreement",
                "asset purchase"
            ]

            # Use specific TA terms (top 10) + general terms
            ta_terms = [ta_name] + ta_includes[:10] + ["biotech", "pharma", "biopharma"]

            # Create targeted queries for each deal type + TA term
            for ta_term in ta_terms[:8]:  # Top 8 TA terms for max breadth
                for deal_term in deal_terms[:5]:  # Top 5 deal types
                    queries.append(f"{ta_term} {deal_term}")

        else:
            # For RSS feeds, use broad terms
            deal_terms = [
                "acquisition",
                "merger",
                "partnership",
                "collaboration",
                "licensing",
                "deal",
                "agreement"
            ]

            general_terms = ["biotech", "pharma", "pharmaceutical", "biopharma"]

            # Create broad queries: "biotech acquisition", "pharma partnership", etc.
            for general in general_terms[:2]:  # Top 2
                for deal in deal_terms[:3]:  # Top 3
                    queries.append(f"{general} {deal}")

        return queries

    def discover_from_source(
        self, source: Source, query: str, max_pages: int = 3
    ) -> List[dict]:
        """
        Discover URLs from a single source.

        Returns:
            List of article metadata dicts
        """
        discovered = []

        for page in range(1, max_pages + 1):
            # Build search URL
            search_url = source.search_template.format(query=query, page=page)

            logger.info(f"Searching {source.name}: {search_url}")

            # Fetch search results
            response = self.web_client.fetch_safe(search_url)
            if not response:
                logger.warning(f"Failed to fetch {search_url}")
                continue

            # Parse results
            soup = BeautifulSoup(response.content, "lxml")

            # Extract article links (generic selectors, would need to be customized per source)
            links = soup.find_all("a", href=True)

            for link in links:
                href = link.get("href")
                if not href:
                    continue

                # Make absolute URL
                if href.startswith("/"):
                    href = source.base_url + href

                # Basic filtering
                if "news" in href.lower() or "press" in href.lower():
                    discovered.append(
                        {
                            "url": href,
                            "source": source.name,
                            "query": query,
                            "discovered_at": datetime.utcnow().isoformat(),
                        }
                    )

        return discovered

    def discover(self, ta_vocab: dict, max_results: int = 100) -> List[dict]:
        """
        Discover deal URLs from all sources.

        Returns:
            List of discovered article metadata
        """
        if self.use_exhaustive:
            return self._discover_via_exhaustive_crawl(max_results)
        elif self.perplexity_client:
            return self._discover_via_perplexity(ta_vocab, max_results)
        elif self.use_apis:
            return self._discover_via_apis(ta_vocab, max_results)
        else:
            return self._discover_via_free_sources(ta_vocab, max_results)

    def _discover_via_exhaustive_crawl(self, max_results: int = 1000) -> List[dict]:
        """Discover using exhaustive site crawling (RECOMMENDED for complete datasets).

        This crawls ALL articles from priority sites (FierceBiotech, FiercePharma, etc.)
        in the date range, then filters using Perplexity extraction.
        """
        logger.info("Starting exhaustive crawl of all priority sites")

        # Get ALL articles from priority sites
        all_articles = self.exhaustive_crawler.crawl_all_sites()

        logger.info(f"Exhaustive crawl found {len(all_articles)} total articles")
        logger.info("Perplexity will filter these during extraction phase")

        # Return ALL articles - Perplexity extraction will filter for deals
        return all_articles[:max_results]

    def _discover_via_perplexity(self, ta_vocab: dict, max_results: int = 100) -> List[dict]:
        """Discover using Perplexity search for maximum breadth."""
        queries = self.build_search_queries(ta_vocab)
        discovered_urls = []
        seen_urls = set()

        from_date = self.config.START_DATE
        to_date = self.config.end_date_resolved

        # Use more queries with Perplexity for max breadth (it's more accurate)
        for query in queries[:20]:  # Top 20 queries for comprehensive coverage
            if len(discovered_urls) >= max_results:
                break

            logger.info(f"Perplexity search: {query}")
            results = self.perplexity_client.search_deals(
                query=query,
                from_date=from_date,
                to_date=to_date,
                max_results=25  # Get more results per query
            )

            for result in results:
                url = result.get("url")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    discovered_urls.append({
                        "url": url,
                        "source": result.get("source", "Perplexity"),
                        "query": query,
                        "discovered_at": datetime.utcnow().isoformat(),
                        "title": result.get("title"),
                        "published_date": result.get("published_date"),
                        "snippet": result.get("snippet")
                    })

                if len(discovered_urls) >= max_results:
                    break

        logger.info(f"Discovered {len(discovered_urls)} unique URLs via Perplexity (max breadth)")
        return discovered_urls[:max_results]

    def _discover_via_apis(self, ta_vocab: dict, max_results: int = 100) -> List[dict]:
        """Discover using production APIs."""
        queries = self.build_search_queries(ta_vocab)
        discovered_urls = []
        seen_urls = set()

        from_date = self.config.START_DATE
        to_date = self.config.end_date_resolved

        for query in queries:
            if len(discovered_urls) >= max_results:
                break

            results = self.api_registry.search_all(query, from_date, to_date, max_results=50)

            for result in results:
                url = result.get("url")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    discovered_urls.append(
                        {
                            "url": url,
                            "source": result.get("source", "API"),
                            "query": query,
                            "discovered_at": datetime.utcnow().isoformat(),
                            "title": result.get("title"),
                            "published_date": result.get("published_date"),
                        }
                    )

                if len(discovered_urls) >= max_results:
                    break

        logger.info(f"Discovered {len(discovered_urls)} unique URLs via APIs")
        return discovered_urls[:max_results]

    def _discover_via_scraping(self, ta_vocab: dict, max_results: int = 100) -> List[dict]:
        """Discover using web scraping (development/fallback)."""
        queries = self.build_search_queries(ta_vocab)
        all_sources = self.source_registry.get_all_sources()

        discovered_urls = []
        seen_urls = set()

        for source in all_sources:
            for query in queries:
                if len(discovered_urls) >= max_results:
                    break

                results = self.discover_from_source(source, query, max_pages=2)

                for result in results:
                    url = result["url"]
                    if url not in seen_urls:
                        seen_urls.add(url)
                        discovered_urls.append(result)

                if len(discovered_urls) >= max_results:
                    break

        logger.info(f"Discovered {len(discovered_urls)} unique URLs via scraping")
        return discovered_urls[:max_results]

    def _discover_via_free_sources(self, ta_vocab: dict, max_results: int = 100) -> List[dict]:
        """Discover using free sources (Google News + RSS)."""
        queries = self.build_search_queries(ta_vocab)
        discovered_urls = []
        seen_urls = set()

        for query in queries[:5]:  # Top 5 queries only for free sources
            if len(discovered_urls) >= max_results:
                break

            results = self.free_registry.search_all(query, max_results=20)

            for result in results:
                url = result.get('url')
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    discovered_urls.append({
                        'url': url,
                        'source': result.get('source', 'Free'),
                        'query': query,
                        'discovered_at': datetime.utcnow().isoformat(),
                        'title': result.get('title'),
                        'published_date': result.get('published_date'),
                    })

                if len(discovered_urls) >= max_results:
                    break

        logger.info(f"Discovered {len(discovered_urls)} unique URLs via free sources")
        return discovered_urls[:max_results]
