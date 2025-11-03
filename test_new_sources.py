"""Test BioWorld and BioPharmaDealmakers crawling."""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from deal_finder.config_loader import load_config
from deal_finder.discovery.exhaustive_crawler import ExhaustiveSiteCrawler

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Test new sources only."""
    config = load_config("config/config.yaml")
    start_date = config.START_DATE
    end_date = config.end_date_resolved

    logger.info("=" * 80)
    logger.info("Testing BioWorld & BioPharmaDealmakers")
    logger.info("=" * 80)
    logger.info(f"Date Range: {start_date} to {end_date}")

    # Get URL filters from config
    url_filters = config.URL_FILTERS

    crawler = ExhaustiveSiteCrawler(
        from_date=start_date,
        to_date=end_date,
        use_index=False,  # Don't use index for this test
        url_filters=url_filters
    )

    # Test BioWorld
    logger.info("\n" + "=" * 80)
    logger.info("Testing BioWorld")
    logger.info("=" * 80)
    bioworld_articles = crawler.crawl_site('BioWorld')
    logger.info(f"✓ BioWorld: {len(bioworld_articles)} articles")
    if bioworld_articles:
        logger.info(f"  Sample: {bioworld_articles[0]['url']}")

    # Test BioPharmaDealmakers
    logger.info("\n" + "=" * 80)
    logger.info("Testing BioPharmaDealmakers")
    logger.info("=" * 80)
    nature_articles = crawler.crawl_site('BioPharmaDealmakers')
    logger.info(f"✓ BioPharmaDealmakers: {len(nature_articles)} articles")
    if nature_articles:
        logger.info(f"  Sample: {nature_articles[0]['url']}")

    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("✅ TEST COMPLETE!")
    logger.info("=" * 80)
    logger.info(f"BioWorld: {len(bioworld_articles)} articles")
    logger.info(f"BioPharmaDealmakers: {len(nature_articles)} articles")

    if bioworld_articles:
        logger.info("\nBioWorld samples:")
        for i, article in enumerate(bioworld_articles[:3], 1):
            logger.info(f"  {i}. {article['url']}")

    if nature_articles:
        logger.info("\nBioPharmaDealmakers samples:")
        for i, article in enumerate(nature_articles[:3], 1):
            logger.info(f"  {i}. {article['url']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
