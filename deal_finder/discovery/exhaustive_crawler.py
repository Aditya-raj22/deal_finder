"""Exhaustive site crawler for comprehensive deal coverage."""

import gzip
import logging
import re
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict
from xml.etree import ElementTree as ET

import requests
from bs4 import BeautifulSoup

from .url_index import URLIndex

logger = logging.getLogger(__name__)


class ExhaustiveSiteCrawler:
    """Crawl specific sites exhaustively to get ALL articles in date range."""

    # Reliable biotech/pharma news sites with RSS/XML feeds
    # ALL 7 SITES - Deduplication handled in pipeline
    PRIORITY_SITES = {
        'FierceBiotech': {
            'rss_feeds': [
                'https://www.fiercebiotech.com/rss/xml',
                'https://www.fiercebiotech.com/deals/rss',
                'https://www.fiercebiotech.com/partnering/rss',
                'https://www.fiercebiotech.com/regulatory/rss',
            ],
            'sitemap': 'https://www.fiercebiotech.com/sitemap.xml',
            'archive_pattern': 'https://www.fiercebiotech.com/archives/{year}/{month}'
        },
        'FiercePharma': {
            'rss_feeds': [
                'https://www.fiercepharma.com/rss/xml',
                'https://www.fiercepharma.com/m-a/rss',
                'https://www.fiercepharma.com/partnering/rss',
            ],
            'sitemap': 'https://www.fiercepharma.com/sitemap.xml',
            'archive_pattern': 'https://www.fiercepharma.com/archives/{year}/{month}'
        },
        'GEN': {
            'rss_feeds': [
                'https://www.genengnews.com/feed/',
                'https://www.genengnews.com/topics/bioprocessing/feed/',
                'https://www.genengnews.com/topics/drug-discovery/feed/',
            ],
            'sitemap': 'https://www.genengnews.com/sitemap.xml',
        },
        'BioPharma Dive': {
            'rss_feeds': [
                'https://www.biopharmadive.com/feeds/news/',
            ],
            'sitemap': 'https://www.biopharmadive.com/sitemap.xml',
            # Skip old archives - only fetch 2021+ monthly archives
            'skip_old_archives': True,
            'min_archive_year': 2021,
        },
        'Endpoints News': {
            'rss_feeds': [
                'https://endpts.com/feed/',
            ],
            'sitemap': 'https://endpts.com/sitemap.xml',
            # Increase sub-sitemap depth to capture more articles
            'max_subsitemaps': 40,
        },
        # 'BioWorld': {
        #     'rss_feeds': [
        #         'https://www.bioworld.com/rss',
        #     ],
        #     'sitemap': 'https://www.bioworld.com/sitemap.xml',
        # },
        'BioPharmaDealmakers': {
            'rss_feeds': [
                'https://www.nature.com/biopharmdeal.rss',
            ],
            'sitemap': 'https://www.nature.com/biopharmdeal/sitemap.xml',
        },
    }

    def __init__(
        self,
        from_date: str,
        to_date: str,
        timeout: int = 30,
        use_index: bool = True,
        index_path: Optional[Path] = None,
        url_filters: Optional[Dict[str, Dict[str, List[str]]]] = None
    ):
        """Initialize exhaustive crawler.

        Args:
            from_date: Start date (YYYY-MM-DD)
            to_date: End date (YYYY-MM-DD)
            timeout: Request timeout in seconds
            use_index: Use URL index for incremental crawling (default: True)
            index_path: Path to index file (default: output/url_index.json)
            url_filters: Per-site URL filters with 'allow' and 'block' regex patterns
        """
        # Parse dates and make them timezone-aware (UTC) for comparison
        from datetime import timezone
        self.from_date = datetime.strptime(from_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        self.to_date = datetime.strptime(to_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        self.timeout = timeout
        self.use_index = use_index
        self.url_index = URLIndex(index_path) if use_index else None
        self.url_filters = url_filters or {}

        # Compile regex patterns for efficiency
        self._compiled_filters = {}
        for site_name, filters in self.url_filters.items():
            self._compiled_filters[site_name] = {
                'allow': [re.compile(pattern) for pattern in filters.get('allow', [])],
                'block': [re.compile(pattern) for pattern in filters.get('block', [])]
            }

        # Reusable Selenium client (initialized on first use)
        self._selenium_client = None

        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })

        if use_index:
            logger.info(f"Incremental crawling enabled: {self.url_index.get_stats()}")

    def _should_include_url(self, url: str, site_name: str) -> bool:
        """Check if URL should be included based on allow/block patterns.

        Args:
            url: URL to check
            site_name: Name of the site

        Returns:
            True if URL should be included, False otherwise
        """
        if site_name not in self._compiled_filters:
            return True  # No filters = include all

        filters = self._compiled_filters[site_name]

        # Check block patterns first (faster to exclude)
        for block_pattern in filters['block']:
            if block_pattern.search(url):
                return False

        # Check allow patterns (must match at least one if any are defined)
        if filters['allow']:
            for allow_pattern in filters['allow']:
                if allow_pattern.search(url):
                    return True
            return False  # Had allow patterns but none matched

        return True  # No allow patterns = include (already passed block check)

    def _fetch_rss_feed(self, feed_url: str) -> List[dict]:
        """Fetch all articles from RSS feed.

        Returns:
            List of article dicts with url, title, published_date
        """
        try:
            response = self.session.get(feed_url, timeout=self.timeout)
            response.raise_for_status()

            root = ET.fromstring(response.content)
            articles = []

            # Try RSS 2.0 format
            for item in root.findall('.//item'):
                title = item.find('title')
                link = item.find('link')
                pubDate = item.find('pubDate')

                if link is not None and link.text:
                    # Parse date if available
                    published_date = None
                    if pubDate is not None and pubDate.text:
                        try:
                            # Try parsing RFC 2822 format
                            from email.utils import parsedate_to_datetime
                            published_date = parsedate_to_datetime(pubDate.text)
                        except:
                            pass

                    # Filter by date range
                    if published_date:
                        if not (self.from_date <= published_date <= self.to_date):
                            continue

                    articles.append({
                        'url': link.text.strip(),
                        'title': title.text.strip() if title is not None and title.text else '',
                        'published_date': published_date.strftime("%Y-%m-%d") if published_date else None,
                        'source': 'RSS'
                    })

            # Try Atom format
            if not articles:
                for entry in root.findall('.//{http://www.w3.org/2005/Atom}entry'):
                    title = entry.find('{http://www.w3.org/2005/Atom}title')
                    link = entry.find('{http://www.w3.org/2005/Atom}link')
                    updated = entry.find('{http://www.w3.org/2005/Atom}updated')

                    if link is not None:
                        href = link.get('href', '')
                        if href:
                            # Parse date
                            published_date = None
                            if updated is not None and updated.text:
                                try:
                                    published_date = datetime.fromisoformat(updated.text.replace('Z', '+00:00'))
                                except:
                                    pass

                            # Filter by date range
                            if published_date:
                                if not (self.from_date <= published_date <= self.to_date):
                                    continue

                            articles.append({
                                'url': href,
                                'title': title.text.strip() if title is not None and title.text else '',
                                'published_date': published_date.strftime("%Y-%m-%d") if published_date else None,
                                'source': 'RSS'
                            })

            logger.info(f"Fetched {len(articles)} articles from {feed_url}")
            return articles

        except Exception as e:
            logger.warning(f"Failed to fetch RSS feed {feed_url}: {e}")
            return []

    def _get_selenium_client(self):
        """Get or create reusable Selenium client."""
        if self._selenium_client is None:
            from ..utils.selenium_client import SeleniumWebClient
            self._selenium_client = SeleniumWebClient(headless=True, timeout=30)
            logger.info("Initialized Selenium client (will be reused)")
        return self._selenium_client

    def _fetch_sitemap_selenium(self, sitemap_url: str, site_name: str = None, site_config: dict = None) -> List[dict]:
        """Fetch sitemap using Selenium to bypass Cloudflare.

        Returns:
            List of article dicts
        """
        try:
            # Reuse existing Selenium client
            web_client = self._get_selenium_client()
            xml_content = web_client.fetch(sitemap_url)

            if not xml_content:
                logger.warning(f"Selenium failed to fetch sitemap: {sitemap_url}")
                return []

            # Parse XML
            root = ET.fromstring(xml_content.encode('utf-8'))
            articles = []

            # Handle sitemap index (links to other sitemaps)
            sitemap_locs = root.findall('.//{http://www.sitemaps.org/schemas/sitemap/0.9}sitemap/{http://www.sitemaps.org/schemas/sitemap/0.9}loc')
            if sitemap_locs:
                # Get max_sitemaps from site config (default 10)
                max_sitemaps = site_config.get('max_subsitemaps', 10) if site_config else 10
                total_sitemaps = len(sitemap_locs)

                # Filter out old BioPharma Dive archives if configured
                if site_config and site_config.get('skip_old_archives') and site_config.get('min_archive_year'):
                    min_year = site_config['min_archive_year']
                    filtered_locs = []
                    for loc in sitemap_locs:
                        url = loc.text
                        # Skip sitemap-topics.xml and sitemap-footer.xml for BioPharma Dive
                        if 'sitemap-topics' in url or 'sitemap-footer' in url:
                            logger.info(f"  Skipping non-article sitemap: {url}")
                            continue
                        # Check for year in URL (e.g., sitemap-2016-01.xml)
                        import re
                        year_match = re.search(r'sitemap-(\d{4})', url)
                        if year_match:
                            year = int(year_match.group(1))
                            if year < min_year:
                                logger.info(f"  Skipping old archive: {url} (year {year} < {min_year})")
                                continue
                        filtered_locs.append(loc)
                    sitemap_locs = filtered_locs
                    logger.info(f"  Filtered to {len(sitemap_locs)} relevant sitemaps (from {total_sitemaps})")

                # Limit to max_subsitemaps
                sitemap_locs = sitemap_locs[:max_sitemaps]

                logger.info(f"Found sitemap index with {total_sitemaps} sub-sitemaps (fetching first {len(sitemap_locs)})")
                for i, sitemap_loc in enumerate(sitemap_locs, 1):
                    logger.info(f"  Fetching sub-sitemap {i}/{len(sitemap_locs)}: {sitemap_loc.text}")
                    sub_articles = self._fetch_sitemap(sitemap_loc.text, site_name, site_config)  # Recursive
                    articles.extend(sub_articles)
                    time.sleep(1)  # Reduced rate limiting (reusing browser)

                if len(sitemap_locs) < total_sitemaps:
                    logger.info(f"  Skipped {total_sitemaps - len(sitemap_locs)} sub-sitemaps")

                return articles

            # Handle regular sitemap (list of URLs)
            urls = root.findall('.//{http://www.sitemaps.org/schemas/sitemap/0.9}url')
            filtered_count = 0
            for url in urls:
                loc = url.find('{http://www.sitemaps.org/schemas/sitemap/0.9}loc')
                lastmod = url.find('{http://www.sitemaps.org/schemas/sitemap/0.9}lastmod')

                if loc is not None and loc.text:
                    url_str = loc.text.strip()

                    # Apply URL filtering if site_name provided
                    if site_name and not self._should_include_url(url_str, site_name):
                        filtered_count += 1
                        continue

                    # Parse last modified date
                    published_date = None
                    if lastmod is not None and lastmod.text:
                        try:
                            published_date = datetime.fromisoformat(lastmod.text.replace('Z', '+00:00'))
                        except:
                            pass

                    # Filter by date range - but INCLUDE if no date (better to over-include)
                    if published_date:
                        if not (self.from_date <= published_date <= self.to_date):
                            continue

                    articles.append({
                        'url': url_str,
                        'title': '',
                        'published_date': published_date.strftime("%Y-%m-%d") if published_date else None,
                        'source': 'Sitemap'
                    })

            if filtered_count > 0:
                logger.info(f"Selenium: Filtered out {filtered_count} URLs based on allow/block patterns")
            logger.info(f"Selenium fetched {len(articles)} URLs from sitemap")
            return articles

        except Exception as e:
            logger.warning(f"Selenium sitemap fetch failed for {sitemap_url}: {e}")
            return []

    def _fetch_sitemap(self, sitemap_url: str, site_name: str = None, site_config: dict = None) -> List[dict]:
        """Fetch all article URLs from XML sitemap.

        Args:
            sitemap_url: URL of the sitemap
            site_name: Name of the site (for filtering)
            site_config: Site configuration dict

        Returns:
            List of article dicts with url, lastmod
        """
        try:
            # Try requests first (fast)
            response = self.session.get(sitemap_url, timeout=self.timeout)

            # If blocked by Cloudflare, use Selenium
            if response.status_code == 403:
                logger.info(f"Sitemap blocked by Cloudflare, using Selenium: {sitemap_url}")
                return self._fetch_sitemap_selenium(sitemap_url, site_name, site_config)

            response.raise_for_status()

            # Decompress if gzipped (BioWorld uses .xml.gz)
            content = response.content
            if sitemap_url.endswith('.gz'):
                try:
                    content = gzip.decompress(content)
                    logger.debug(f"Decompressed gzipped sitemap: {sitemap_url}")
                except Exception as e:
                    logger.warning(f"Failed to decompress gzipped sitemap {sitemap_url}: {e}")
                    return []

            root = ET.fromstring(content)
            articles = []

            # Handle sitemap index (links to other sitemaps)
            sitemap_locs = root.findall('.//{http://www.sitemaps.org/schemas/sitemap/0.9}sitemap/{http://www.sitemaps.org/schemas/sitemap/0.9}loc')
            if sitemap_locs:
                # Get max_sitemaps from site config (default 10)
                max_sitemaps = site_config.get('max_subsitemaps', 10) if site_config else 10
                total_sitemaps = len(sitemap_locs)

                # Filter out old BioPharma Dive archives if configured
                if site_config and site_config.get('skip_old_archives') and site_config.get('min_archive_year'):
                    min_year = site_config['min_archive_year']
                    filtered_locs = []
                    for loc in sitemap_locs:
                        url = loc.text
                        # Skip sitemap-topics.xml and sitemap-footer.xml for BioPharma Dive
                        if 'sitemap-topics' in url or 'sitemap-footer' in url:
                            logger.info(f"  Skipping non-article sitemap: {url}")
                            continue
                        # Check for year in URL (e.g., sitemap-2016-01.xml)
                        year_match = re.search(r'sitemap-(\d{4})', url)
                        if year_match:
                            year = int(year_match.group(1))
                            if year < min_year:
                                logger.info(f"  Skipping old archive: {url} (year {year} < {min_year})")
                                continue
                        filtered_locs.append(loc)
                    sitemap_locs = filtered_locs
                    logger.info(f"  Filtered to {len(sitemap_locs)} relevant sitemaps (from {total_sitemaps})")

                # Limit to max_subsitemaps
                sitemap_locs = sitemap_locs[:max_sitemaps]

                logger.info(f"Found sitemap index with {total_sitemaps} sub-sitemaps (fetching first {len(sitemap_locs)})")
                for i, sitemap_loc in enumerate(sitemap_locs, 1):
                    logger.info(f"  Fetching sub-sitemap {i}/{len(sitemap_locs)}: {sitemap_loc.text}")
                    sub_articles = self._fetch_sitemap(sitemap_loc.text, site_name, site_config)
                    articles.extend(sub_articles)
                    time.sleep(2)  # Rate limiting - be respectful

                if len(sitemap_locs) < total_sitemaps:
                    logger.info(f"  Skipped {total_sitemaps - len(sitemap_locs)} sub-sitemaps")

                logger.info(f"Completed {len(sitemap_locs)} sub-sitemaps, total articles: {len(articles)}")
                return articles

            # Handle regular sitemap (list of URLs)
            urls = root.findall('.//{http://www.sitemaps.org/schemas/sitemap/0.9}url')
            filtered_count = 0
            for url in urls:
                loc = url.find('{http://www.sitemaps.org/schemas/sitemap/0.9}loc')
                lastmod = url.find('{http://www.sitemaps.org/schemas/sitemap/0.9}lastmod')

                if loc is not None and loc.text:
                    url_str = loc.text.strip()

                    # Apply URL filtering if site_name provided
                    if site_name and not self._should_include_url(url_str, site_name):
                        filtered_count += 1
                        continue

                    # Parse last modified date
                    published_date = None
                    if lastmod is not None and lastmod.text:
                        try:
                            from datetime import timezone
                            # Parse and ensure timezone-aware
                            dt_str = lastmod.text.replace('Z', '+00:00')
                            published_date = datetime.fromisoformat(dt_str)
                            # If naive, make it UTC
                            if published_date.tzinfo is None:
                                published_date = published_date.replace(tzinfo=timezone.utc)
                        except:
                            pass

                    # Filter by date range
                    if published_date:
                        if not (self.from_date <= published_date <= self.to_date):
                            continue

                    articles.append({
                        'url': url_str,
                        'title': '',
                        'published_date': published_date.strftime("%Y-%m-%d") if published_date else None,
                        'source': 'Sitemap'
                    })

            if filtered_count > 0:
                logger.info(f"Filtered out {filtered_count} URLs based on allow/block patterns")
            logger.info(f"Fetched {len(articles)} URLs from sitemap {sitemap_url}")
            return articles

        except Exception as e:
            logger.warning(f"Failed to fetch sitemap {sitemap_url}: {e}")
            return []

    def crawl_site(self, site_name: str) -> List[dict]:
        """Exhaustively crawl a single site for all articles.

        Args:
            site_name: Name of site (key in PRIORITY_SITES)

        Returns:
            List of all article dicts from that site
        """
        if site_name not in self.PRIORITY_SITES:
            logger.error(f"Unknown site: {site_name}")
            return []

        site_config = self.PRIORITY_SITES[site_name]
        all_articles = []
        seen_urls = set()

        logger.info(f"Starting exhaustive crawl of {site_name}")

        # PRIMARY: Fetch from sitemap (complete coverage)
        sitemap_url = site_config.get('sitemap')
        if sitemap_url:
            logger.info(f"  Fetching sitemap: {sitemap_url}")
            articles = self._fetch_sitemap(sitemap_url, site_name, site_config)
            for article in articles:
                url = article['url']
                if url not in seen_urls:
                    seen_urls.add(url)
                    article['source'] = site_name
                    all_articles.append(article)

        # SUPPLEMENTAL: Fetch from archive pages (if available)
        # DISABLED: Archives also blocked by Cloudflare, sitemaps are sufficient
        # archive_pattern = site_config.get('archive_pattern')
        # if archive_pattern:
        #     logger.info(f"  Fetching archive pages for date range")
        #     archive_articles = self._fetch_archive_pages(archive_pattern, site_name)
        #     for article in archive_articles:
        #         url = article['url']
        #         if url not in seen_urls:
        #             seen_urls.add(url)
        #             article['source'] = site_name
        #             all_articles.append(article)

        # FALLBACK: Only use RSS if sitemap AND archive failed
        if len(all_articles) == 0:
            logger.warning(f"  Sitemap and archive returned no articles, falling back to RSS feeds")
            for feed_url in site_config.get('rss_feeds', []):
                articles = self._fetch_rss_feed(feed_url)
                for article in articles:
                    url = article['url']
                    if url not in seen_urls:
                        seen_urls.add(url)
                        article['source'] = site_name
                        all_articles.append(article)
                time.sleep(2)  # Rate limiting

        logger.info(f"Crawled {site_name}: found {len(all_articles)} unique articles")
        return all_articles

    def _fetch_archive_pages(self, archive_pattern: str, site_name: str) -> List[dict]:
        """Fetch articles from archive pages.

        Args:
            archive_pattern: URL pattern with {year}/{month} placeholders
            site_name: Name of site

        Returns:
            List of article dicts
        """
        articles = []
        seen_urls = set()

        # Generate year/month combinations in date range
        current_date = self.from_date
        while current_date <= self.to_date:
            year = current_date.year
            month = current_date.month

            archive_url = archive_pattern.format(year=year, month=f"{month:02d}")
            logger.info(f"    Fetching archive: {year}-{month:02d}")

            try:
                response = self.session.get(archive_url, timeout=self.timeout)
                response.raise_for_status()

                # Parse HTML to extract article links
                soup = BeautifulSoup(response.content, 'lxml')

                # Generic article link extraction (adjust selectors per site)
                link_selectors = [
                    'article a[href]',
                    '.article-title a[href]',
                    '.headline a[href]',
                    'h2 a[href]',
                    'h3 a[href]',
                ]

                for selector in link_selectors:
                    links = soup.select(selector)
                    for link in links:
                        href = link.get('href')
                        if href and href not in seen_urls:
                            # Make absolute URL
                            if href.startswith('/'):
                                from urllib.parse import urlparse
                                parsed = urlparse(archive_url)
                                href = f"{parsed.scheme}://{parsed.netloc}{href}"

                            if href.startswith('http') and href not in seen_urls:
                                seen_urls.add(href)
                                articles.append({
                                    'url': href,
                                    'title': link.get_text().strip(),
                                    'published_date': f"{year}-{month:02d}-01",
                                    'source': 'Archive'
                                })

                time.sleep(3)  # Rate limiting

            except Exception as e:
                logger.warning(f"    Failed to fetch archive {year}-{month:02d}: {e}")

            # Move to next month (keep timezone-aware)
            from datetime import timezone
            if month == 12:
                current_date = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
            else:
                current_date = datetime(year, month + 1, 1, tzinfo=timezone.utc)

        logger.info(f"    Archive crawl found {len(articles)} articles")
        return articles

    def crawl_all_sites(self) -> List[dict]:
        """Exhaustively crawl ALL priority sites with incremental support.

        Returns:
            List of NEW articles (not previously crawled if index enabled)
        """
        all_articles = []
        seen_urls = set()

        for site_name in self.PRIORITY_SITES.keys():
            articles = self.crawl_site(site_name)

            # Filter for new URLs if index enabled
            if self.use_index:
                new_articles = []
                for article in articles:
                    url = article['url']
                    if not self.url_index.is_crawled(url) and url not in seen_urls:
                        seen_urls.add(url)
                        new_articles.append(article)
                        # Mark as crawled immediately (will be saved at end)
                        self.url_index.mark_crawled(url, {
                            'source': site_name,
                            'published_date': article.get('published_date')
                        })

                logger.info(f"{site_name}: {len(new_articles)} new URLs (out of {len(articles)} total)")
                all_articles.extend(new_articles)
            else:
                # No index - return all articles
                for article in articles:
                    url = article['url']
                    if url not in seen_urls:
                        seen_urls.add(url)
                        all_articles.append(article)

            time.sleep(3)  # Rate limiting between sites

        # Save updated index
        if self.use_index:
            self.url_index.save()
            logger.info(f"Total new articles: {len(all_articles)} (index now has {len(self.url_index.crawled_urls)} URLs)")
        else:
            logger.info(f"Total articles from all sites: {len(all_articles)}")

        # Close Selenium client if it was used
        if self._selenium_client:
            self._selenium_client.close()
            logger.info("Closed Selenium client")

        return all_articles
