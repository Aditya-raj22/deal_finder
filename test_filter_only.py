"""
Test keyword filter on existing articles without running Perplexity.
Loads articles from checkpoint and tests different filter settings.
"""

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from deal_finder.keyword_filter import KeywordFilter

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Test filter on checkpoint articles."""

    # Load checkpoint
    checkpoint_file = Path("output/fetch_checkpoint.json")
    if not checkpoint_file.exists():
        logger.error("No checkpoint file found!")
        return 1

    logger.info("Loading articles from checkpoint...")
    with open(checkpoint_file) as f:
        checkpoint_data = json.load(f)
        articles = checkpoint_data.get("articles", [])

    logger.info(f"Loaded {len(articles)} articles from checkpoint")

    # Load keywords
    keywords_file = Path("config/generated_keywords.json")
    with open(keywords_file) as f:
        keyword_data = json.load(f)

    ta_keywords = keyword_data["keywords"]["ta_keywords"]
    stage_keywords = keyword_data["keywords"]["stage_keywords"]
    deal_keywords = keyword_data["keywords"]["deal_keywords"]

    # Test different filter settings
    test_configs = [
        {"name": "Current (loose)", "min_ta": 1, "min_deal": 1},
        {"name": "Stricter TA", "min_ta": 2, "min_deal": 1},
        {"name": "Stricter Deal", "min_ta": 1, "min_deal": 2},
        {"name": "Both Stricter", "min_ta": 2, "min_deal": 2},
        {"name": "Very Strict", "min_ta": 3, "min_deal": 2},
    ]

    logger.info("\n" + "=" * 80)
    logger.info("TESTING DIFFERENT FILTER SETTINGS")
    logger.info("=" * 80)

    for config in test_configs:
        logger.info(f"\n{config['name']}: min_ta_matches={config['min_ta']}, min_deal_matches={config['min_deal']}")

        keyword_filter = KeywordFilter(
            ta_keywords=ta_keywords,
            stage_keywords=stage_keywords,
            deal_keywords=deal_keywords,
            require_deal_keyword=True,
            min_ta_matches=config['min_ta'],
            min_deal_matches=config['min_deal']
        )

        filter_results = keyword_filter.filter_articles(articles)
        passed = len(filter_results["passed"])
        total = len(articles)
        cost = passed * 0.06

        logger.info(f"  Results: {passed}/{total} passed ({passed/total*100:.1f}%)")
        logger.info(f"  Estimated Perplexity cost: ${cost:.2f}")

    logger.info("\n" + "=" * 80)
    logger.info("RECOMMENDATION")
    logger.info("=" * 80)
    logger.info("Choose setting that gives 400-800 articles (budget ~$24-48)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
