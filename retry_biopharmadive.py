"""
Retry BioPharmaDive URLs with aggressive rate limiting and consolidate all articles.

This script:
1. Loads existing checkpoint with all fetched articles
2. Identifies failed BioPharmaDive URLs (status 429)
3. Re-fetches them with 2-second delays
4. Consolidates all articles
5. Performs title deduplication
"""

import json
import logging
import time
from pathlib import Path
from bs4 import BeautifulSoup
from collections import defaultdict

from deal_finder.utils.selenium_client import SeleniumWebClient

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def deduplicate_by_title(articles: list) -> list:
    """Remove duplicate articles based on title similarity."""
    from difflib import SequenceMatcher

    unique_articles = []
    seen_titles = []
    duplicates_removed = 0

    for article in articles:
        title = article.get("title", "").lower().strip()

        # Skip deduplication if title is empty or too short
        if not title or len(title) < 10:
            unique_articles.append(article)
            continue

        # Check if similar title already seen
        is_duplicate = False
        for seen_title in seen_titles:
            similarity = SequenceMatcher(None, title, seen_title).ratio()
            if similarity > 0.8:  # 80% similar = duplicate
                is_duplicate = True
                duplicates_removed += 1
                logger.debug(f"Duplicate found: '{title}' similar to '{seen_title}'")
                break

        if not is_duplicate:
            unique_articles.append(article)
            seen_titles.append(title)

    logger.info(f"Title deduplication: {len(articles)} → {len(unique_articles)} ({duplicates_removed} removed)")
    return unique_articles


def main():
    logger.info("=" * 80)
    logger.info("Retry BioPharmaDive + Consolidate + Deduplicate")
    logger.info("=" * 80)

    # Load checkpoint
    checkpoint_file = Path("output/fetch_checkpoint.json")
    if not checkpoint_file.exists():
        logger.error("No checkpoint found! Run step2 first.")
        return 1

    logger.info("Loading checkpoint...")
    with open(checkpoint_file) as f:
        checkpoint_data = json.load(f)

    all_articles = checkpoint_data.get("articles", [])
    fetched_urls = set(checkpoint_data.get("fetched_urls", []))

    logger.info(f"✓ Loaded {len(all_articles)} articles from checkpoint")
    logger.info(f"✓ {len(fetched_urls)} URLs already fetched")

    # Load URL index to get BioPharmaDive URLs
    from deal_finder.discovery.url_index import URLIndex
    url_index = URLIndex()
    all_urls_meta = url_index.get_all_urls_with_metadata()

    # Find BioPharmaDive URLs that failed (check both source names)
    biopharmadive_failed = [
        meta for meta in all_urls_meta
        if ("biopharmadive.com" in meta["url"].lower() or
            meta.get("source") in ["BioPharmaDive", "BioPharma Dive"])
        and meta["url"] not in fetched_urls
    ]

    logger.info(f"\nTotal URLs in index: {len(all_urls_meta)}")
    logger.info(f"Already fetched: {len(fetched_urls)}")
    logger.info(f"BioPharmaDive URLs to retry: {len(biopharmadive_failed)}")

    if not biopharmadive_failed:
        logger.info("No failed BioPharmaDive URLs - proceeding to consolidation")
    else:
        # Re-fetch with aggressive rate limiting
        logger.info("\n" + "=" * 80)
        logger.info("Re-fetching BioPharmaDive with 1-second delays")
        logger.info("=" * 80)

        web_client = SeleniumWebClient(headless=True, timeout=10)
        refetched = 0
        refetch_failures = 0

        for i, article_meta in enumerate(biopharmadive_failed, 1):
            url = article_meta["url"]

            try:
                # Add 1-second delay BEFORE each request
                time.sleep(1)

                html = web_client.fetch(url)
                if not html:
                    refetch_failures += 1
                    continue

                soup = BeautifulSoup(html, "lxml")
                text = soup.get_text(separator=" ", strip=True)

                if len(text) < 500:
                    continue

                article = {
                    "url": url,
                    "title": article_meta.get("title", ""),
                    "published_date": article_meta.get("published_date", ""),
                    "content": text[:20000],
                    "source": article_meta.get("source", "BioPharmaDive")
                }
                all_articles.append(article)
                fetched_urls.add(url)
                refetched += 1

                if i % 10 == 0:
                    logger.info(f"Progress: {i}/{len(biopharmadive_failed)} ({refetched} success, {refetch_failures} failed)")

            except Exception as e:
                logger.warning(f"Failed to fetch {url}: {e}")
                refetch_failures += 1

        web_client.close()
        logger.info(f"✓ Re-fetched {refetched} BioPharmaDive articles ({refetch_failures} still failed)")

    # Consolidate and count by source
    logger.info("\n" + "=" * 80)
    logger.info("Consolidation Summary")
    logger.info("=" * 80)

    source_counts = defaultdict(int)
    for article in all_articles:
        source = article.get("source", "Unknown")
        source_counts[source] += 1

    logger.info(f"Total articles: {len(all_articles)}")
    for source, count in sorted(source_counts.items()):
        logger.info(f"  {source}: {count}")

    # Title deduplication
    logger.info("\n" + "=" * 80)
    logger.info("Title Deduplication")
    logger.info("=" * 80)

    all_articles = deduplicate_by_title(all_articles)

    # Save consolidated checkpoint
    logger.info("\n" + "=" * 80)
    logger.info("Saving Consolidated Checkpoint")
    logger.info("=" * 80)

    consolidated_checkpoint = {
        "fetched_urls": list(fetched_urls),
        "articles": all_articles,
        "timestamp": checkpoint_data.get("timestamp"),
        "consolidated": True
    }

    with open(checkpoint_file, 'w') as f:
        json.dump(consolidated_checkpoint, f)

    logger.info(f"✓ Saved {len(all_articles)} deduplicated articles to {checkpoint_file}")
    logger.info("\n✅ Done! Run step2 with --skip-crawl --filter-only to continue pipeline")

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
