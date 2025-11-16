"""Build article cache with ChromaDB + MPNet embeddings (best accuracy)."""

import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from queue import Queue
from datetime import datetime, timezone

from bs4 import BeautifulSoup
from deal_finder.discovery.exhaustive_crawler import ExhaustiveSiteCrawler
from deal_finder.utils.selenium_client import SeleniumWebClient
from deal_finder.storage.article_cache_chroma import ChromaArticleCache
from deal_finder.config_loader import load_config

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def build_cache(start_date="2021-01-01", end_date=None, config_path="config/config.yaml"):
    """Build ChromaDB cache with MPNet embeddings."""
    end_date = end_date or datetime.now(timezone.utc).date().isoformat()

    logger.info(f"Building ChromaDB cache: {start_date} to {end_date}")
    config = load_config(config_path)

    # Initialize ChromaDB with better model
    cache = ChromaArticleCache(embedding_model="all-mpnet-base-v2")
    logger.info("Initialized ChromaDB with all-mpnet-base-v2")

    # Crawl URLs
    crawler = ExhaustiveSiteCrawler(
        from_date=start_date,
        to_date=end_date,
        url_filters=config.URL_FILTERS,
        use_index=True
    )

    logger.info("Discovering URLs...")
    all_urls = crawler.crawl_all_sites()
    urls_to_fetch = [u for u in all_urls if not cache.article_exists(u['url'])]
    logger.info(f"Found {len(all_urls)} URLs, {len(urls_to_fetch)} new to fetch")

    # Parallel fetch
    web_pool = Queue()
    for _ in range(10):
        web_pool.put(SeleniumWebClient(headless=True, timeout=5))

    lock = Lock()
    articles = []
    skipped = [0]

    def fetch(url_data):
        client = web_pool.get()
        try:
            html = client.fetch(url_data['url'])
            if not html:
                return None

            text = BeautifulSoup(html, "lxml").get_text(separator=" ", strip=True)
            if len(text) < 500:
                return None

            pub_date = url_data.get('published_date') or end_date
            if pub_date < start_date:
                return None

            return {
                'url': url_data['url'],
                'title': url_data.get('title', ''),
                'content': text[:2500],
                'published_date': pub_date,
                'source': url_data.get('source', 'Unknown'),
                'lastmod': url_data.get('lastmod')
            }
        except:
            return None
        finally:
            web_pool.put(client)

    logger.info(f"Fetching {len(urls_to_fetch)} articles with 10 workers...")
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(fetch, u) for u in urls_to_fetch]
        for future in as_completed(futures):
            article = future.result()
            if article:
                with lock:
                    articles.append(article)
                    if len(articles) % 100 == 0:
                        logger.info(f"Fetched: {len(articles)}/{len(urls_to_fetch)}")
            else:
                skipped[0] += 1

    # Batch insert to ChromaDB (with automatic embedding computation)
    logger.info(f"Inserting {len(articles)} articles with embeddings...")
    cache.upsert_batch(articles, batch_size=100)

    logger.info(f"✓ Complete! {len(articles)} cached, {skipped[0]} skipped")
    logger.info(f"Stats: {cache.get_stats()}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", default="2021-01-01")
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--config", default="config/config.yaml")
    args = parser.parse_args()

    Path("logs").mkdir(exist_ok=True)
    build_cache(args.start_date, args.end_date, args.config)
