"""Test Perplexity's search capability - let IT find and extract deals."""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_perplexity_search():
    """Test Perplexity's online search to find and extract deals."""
    import os
    from deal_finder.perplexity_client import PerplexityClient
    from deal_finder.config_loader import load_config, load_ta_vocab

    logger.info("=" * 70)
    logger.info("PERPLEXITY SEARCH TEST - Let Perplexity Do Everything!")
    logger.info("=" * 70)

    # Check API key
    api_key = os.getenv("PERPLEXITY_API_KEY")
    if not api_key:
        logger.error("\n❌ PERPLEXITY_API_KEY not set!")
        return 1

    logger.info("\n✓ API key found")

    # Load config
    logger.info("\n1. Loading configuration...")
    config_path = Path(__file__).parent / "config" / "config.yaml"
    config = load_config(str(config_path))
    ta_vocab = load_ta_vocab(config)

    ta_name = ta_vocab.get("therapeutic_area", "biotech")
    logger.info(f"   Therapeutic Area: {ta_name}")

    # Initialize Perplexity
    logger.info("\n2. Initializing Perplexity client...")
    client = PerplexityClient(api_key)

    # Test search - let Perplexity find recent deals
    logger.info("\n3. Asking Perplexity to search for recent deals...")
    logger.info("   (Perplexity will search the web and extract deal info)")

    query = f"{ta_name} biotech pharma acquisition merger partnership 2024"
    logger.info(f"   Search query: {query}")

    results = client.search_deals(
        query=query,
        from_date="2024-01-01",
        to_date="2024-12-31",
        max_results=10
    )

    if not results:
        logger.warning("\n⚠ No results found")
        logger.info("This might mean:")
        logger.info("  • Query too specific")
        logger.info("  • Perplexity search didn't find matching articles")
        logger.info("  • Try a broader query")
        return 1

    logger.info(f"\n✅ Found {len(results)} articles!")

    # Display results
    logger.info("\n4. Results from Perplexity search:")
    for i, result in enumerate(results, 1):
        logger.info(f"\n   [{i}] {result.get('title', 'No title')}")
        logger.info(f"       URL: {result.get('url', 'N/A')}")
        logger.info(f"       Date: {result.get('published_date', 'N/A')}")
        logger.info(f"       Snippet: {result.get('snippet', 'N/A')[:100]}...")

    logger.info("\n" + "=" * 70)
    logger.info("✅ PERPLEXITY SEARCH TEST COMPLETE!")
    logger.info("=" * 70)
    logger.info(f"\nPerplexity found {len(results)} potential deal articles.")
    logger.info("These URLs can now be processed for extraction.")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(test_perplexity_search())
    except Exception as e:
        logger.error(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
