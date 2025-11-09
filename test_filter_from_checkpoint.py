"""
Test keyword filter on checkpoint without re-fetching.
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
        logger.error(f"No checkpoint file found at {checkpoint_file}")
        logger.error("You need to run fetch first to create checkpoint!")
        return 1

    logger.info("=" * 80)
    logger.info("LOADING CHECKPOINT")
    logger.info("=" * 80)
    logger.info(f"Loading from: {checkpoint_file}")

    with open(checkpoint_file) as f:
        checkpoint_data = json.load(f)
        articles = checkpoint_data.get("articles", [])

    logger.info(f"✓ Loaded {len(articles)} articles")

    # Load keywords
    keywords_file = Path("config/generated_keywords.json")
    with open(keywords_file) as f:
        keyword_data = json.load(f)

    ta_keywords = keyword_data["keywords"]["ta_keywords"]
    stage_keywords = keyword_data["keywords"]["stage_keywords"]
    deal_keywords = keyword_data["keywords"]["deal_keywords"]

    # Test different filter settings
    logger.info("\n" + "=" * 80)
    logger.info("TESTING FILTER SETTINGS")
    logger.info("=" * 80)

    configs = [
        {"name": "Previous (too loose)", "min_ta": 1, "min_deal": 1, "money": False},
        {"name": "With money req", "min_ta": 2, "min_deal": 2, "money": True},
        {"name": "No money req", "min_ta": 2, "min_deal": 2, "money": False},
        {"name": "Stricter + money", "min_ta": 3, "min_deal": 2, "money": True},
        {"name": "Very strict + money", "min_ta": 3, "min_deal": 3, "money": True},
    ]

    results = []
    for config in configs:
        keyword_filter = KeywordFilter(
            ta_keywords=ta_keywords,
            stage_keywords=stage_keywords,
            deal_keywords=deal_keywords,
            require_deal_keyword=True,
            min_ta_matches=config['min_ta'],
            min_deal_matches=config['min_deal'],
            require_money_mention=config['money']
        )

        filter_results = keyword_filter.filter_articles(articles)
        passed = len(filter_results["passed"])
        total = len(articles)
        cost = passed * 0.06

        results.append({
            "name": config["name"],
            "min_ta": config["min_ta"],
            "min_deal": config["min_deal"],
            "money": config["money"],
            "passed": passed,
            "cost": cost
        })

    # Print summary
    logger.info("\n" + "=" * 80)
    logger.info("RESULTS SUMMARY")
    logger.info("=" * 80)
    logger.info(f"{'Setting':<25} {'min_ta':>7} {'min_deal':>9} {'Money?':>7} {'Articles':>10} {'Cost':>10}")
    logger.info("-" * 80)
    for r in results:
        money_str = "Yes" if r['money'] else "No"
        logger.info(f"{r['name']:<25} {r['min_ta']:>7} {r['min_deal']:>9} {money_str:>7} {r['passed']:>10} ${r['cost']:>9.2f}")

    logger.info("\n" + "=" * 80)
    logger.info("RECOMMENDATION")
    logger.info("=" * 80)
    logger.info("Target: 400-800 articles (budget $24-48)")

    # Find best match
    best = min(results[1:], key=lambda x: abs(x['passed'] - 600))
    logger.info(f"\nBest match: {best['name']}")
    logger.info(f"  Settings: min_ta={best['min_ta']}, min_deal={best['min_deal']}")
    logger.info(f"  Articles: {best['passed']}")
    logger.info(f"  Cost: ${best['cost']:.2f}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
