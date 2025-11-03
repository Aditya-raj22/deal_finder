"""
Test Crawling Only

This script tests the sitemap crawling functionality without fetching content
or doing extraction. It uses existing keywords from config/generated_keywords.json.

Usage:
    python test_crawl_only.py --config config/config.yaml

What it does:
    1. Loads configuration and existing keywords
    2. Crawls all 5 sitemaps (FierceBiotech, FiercePharma, GEN, BioPharma Dive, Endpoints)
    3. Reports how many URLs were found per site
    4. Shows sample URLs from each site

What it DOESN'T do:
    - Fetch article content (no Selenium)
    - Extract deals (no Perplexity)
    - Filter by keywords (tests raw crawling only)
"""

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from deal_finder.config_loader import load_config
from deal_finder.discovery.exhaustive_crawler import ExhaustiveSiteCrawler

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Test crawling functionality only."""
    import argparse

    parser = argparse.ArgumentParser(description="Test Crawling Only")
    parser.add_argument(
        "--config",
        default="config/config.yaml",
        help="Path to config file"
    )
    parser.add_argument(
        "--keywords",
        default="config/generated_keywords.json",
        help="Path to generated keywords file"
    )

    args = parser.parse_args()

    logger.info("=" * 80)
    logger.info("TEST: Crawl All 5 Sitemaps")
    logger.info("=" * 80)

    # Load configuration
    config = load_config(args.config)
    start_date = config.START_DATE
    end_date = config.end_date_resolved

    logger.info(f"Date Range: {start_date} to {end_date}")

    # Check if keywords exist (optional - just for info)
    keywords_file = Path(args.keywords)
    if keywords_file.exists():
        with open(keywords_file) as f:
            keyword_data = json.load(f)
        logger.info(f"\nUsing keywords from: {keywords_file}")
        logger.info(f"  • TA keywords: {len(keyword_data['keywords']['ta_keywords'])}")
        logger.info(f"  • Stage keywords: {len(keyword_data['keywords']['stage_keywords'])}")
        logger.info(f"  • Deal keywords: {len(keyword_data['keywords']['deal_keywords'])}")
    else:
        logger.warning(f"\n⚠ Keywords file not found: {keywords_file}")
        logger.warning("Proceeding with crawl test anyway...")

    # CRAWL ALL 5 SITES
    logger.info("\n" + "=" * 80)
    logger.info("Crawling All 5 Sitemaps")
    logger.info("=" * 80)

    crawler = ExhaustiveSiteCrawler(
        from_date=start_date,
        to_date=end_date,
        use_index=True  # Use incremental crawling
    )

    # Crawl all sites
    discovered_urls = crawler.crawl_all_sites()

    # RESULTS
    logger.info("\n" + "=" * 80)
    logger.info("✅ CRAWL TEST COMPLETE!")
    logger.info("=" * 80)

    logger.info(f"\nTotal URLs discovered: {len(discovered_urls)}")

    # Group by source
    by_source = {}
    for article in discovered_urls:
        source = article.get('source', 'Unknown')
        if source not in by_source:
            by_source[source] = []
        by_source[source].append(article)

    # Report per-site results
    logger.info("\nURLs per site:")
    for source, articles in sorted(by_source.items()):
        logger.info(f"  • {source}: {len(articles)} URLs")

    # Show sample URLs from each site
    logger.info("\nSample URLs (first 2 from each site):")
    for source, articles in sorted(by_source.items()):
        logger.info(f"\n{source}:")
        for i, article in enumerate(articles[:2], 1):
            logger.info(f"  {i}. {article['url']}")
            if article.get('title'):
                logger.info(f"     Title: {article['title'][:80]}...")
            if article.get('published_date'):
                logger.info(f"     Date: {article['published_date']}")

    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("Next Steps:")
    logger.info("=" * 80)
    logger.info("\nIf crawling looks good, you can:")
    logger.info("1. Edit keywords if needed: config/generated_keywords.json")
    logger.info("2. Run full pipeline: python step2_run_pipeline.py")
    logger.info("\nThe full pipeline will:")
    logger.info("  • Fetch content for all URLs (Selenium)")
    logger.info("  • Deduplicate by title (80% similarity)")
    logger.info("  • Filter by keywords (TA + stage + deal)")
    logger.info("  • Extract deals (Perplexity API)")
    logger.info("  • Deduplicate deals (by acquirer + target + date)")
    logger.info("  • Save 2 Excel files (deals + rejected)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
