"""Quick test script - Find 1 deal from FiercePharma only."""

import logging
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def quick_test():
    """Quick test: Process FiercePharma until we find 1 deal."""
    import os
    from bs4 import BeautifulSoup
    from deal_finder.config_loader import load_config
    from deal_finder.discovery.exhaustive_crawler import ExhaustiveSiteCrawler
    from deal_finder.extraction.perplexity_extractor import PerplexityExtractor
    from deal_finder.normalization import CompanyCanonicalizer
    from deal_finder.utils.selenium_client import SeleniumWebClient
    from deal_finder.models import Deal
    from deal_finder.output import ExcelWriter
    import uuid

    logger.info("=" * 60)
    logger.info("QUICK TEST - Find 1 Deal from FiercePharma")
    logger.info("=" * 60)

    # Check Perplexity API key
    api_key = os.getenv("PERPLEXITY_API_KEY")
    if not api_key:
        logger.error("❌ PERPLEXITY_API_KEY not set!")
        logger.info("Set it with: export PERPLEXITY_API_KEY='pplx-...'")
        return 1

    logger.info(f"✓ API key found: {api_key[:10]}...")

    # Load config
    logger.info("\n1. Loading configuration...")
    config_path = Path(__file__).parent / "config" / "config.yaml"
    config = load_config(str(config_path))
    logger.info(f"   Therapeutic Area: {config.THERAPEUTIC_AREA}")
    logger.info(f"   Date Range: {config.START_DATE} to today")

    # Load TA vocab
    from deal_finder.config_loader import load_ta_vocab, load_aliases
    ta_vocab = load_ta_vocab(config)
    aliases = load_aliases(config)
    logger.info(f"   TA includes: {', '.join(ta_vocab['includes'][:5])}...")

    # Initialize crawler (no index for test)
    logger.info("\n2. Initializing FiercePharma crawler...")
    crawler = ExhaustiveSiteCrawler(
        from_date=config.START_DATE,
        to_date=config.end_date_resolved,
        use_index=False  # No index for quick test
    )

    # Get articles from FiercePharma ONLY
    logger.info("\n3. Fetching articles from FiercePharma sitemap...")
    logger.info("   (This may take 1-2 minutes)")
    articles = crawler.crawl_site('FiercePharma')
    logger.info(f"   Found {len(articles)} total articles from FiercePharma")

    # Limit to first 50 articles to speed up test
    articles = articles[:50]
    logger.info(f"   Testing with first {len(articles)} articles")

    # Initialize components
    logger.info("\n4. Initializing extraction components...")
    web_client = SeleniumWebClient(headless=True, timeout=20)
    perplexity_extractor = PerplexityExtractor(api_key=api_key, batch_size=5)
    company_canonicalizer = CompanyCanonicalizer(aliases)

    # Fetch article content
    logger.info(f"\n5. Fetching article content (max {len(articles)})...")
    fetched_articles = []
    for i, article_meta in enumerate(articles, 1):
        url = article_meta["url"]
        logger.info(f"   [{i}/{len(articles)}] Fetching: {url}")

        html = web_client.fetch(url)
        if not html:
            logger.warning(f"   Failed to fetch")
            continue

        # Parse HTML to text
        soup = BeautifulSoup(html, "lxml")
        text = soup.get_text(separator=" ", strip=True)

        # Skip if too short
        if len(text) < 500:
            logger.info(f"   Skipping (too short: {len(text)} chars)")
            continue

        fetched_articles.append({
            "url": url,
            "title": article_meta.get("title", ""),
            "content": text[:20000]
        })

        logger.info(f"   ✓ Fetched ({len(text)} chars)")

        # Process in batches of 5 for efficiency
        if len(fetched_articles) >= 5:
            logger.info(f"\n6. Extracting deals from batch of {len(fetched_articles)} articles...")
            extractions = perplexity_extractor.extract_batch(fetched_articles, ta_vocab)

            # Check for deals
            for extraction in extractions:
                if not extraction:
                    continue

                parsed = perplexity_extractor.parse_extracted_deal(
                    extraction,
                    ta_vocab["therapeutic_area"]
                )

                if parsed:
                    logger.info(f"\n🎉 DEAL FOUND!")
                    logger.info(f"   URL: {parsed['url']}")
                    logger.info(f"   Acquirer: {parsed['acquirer']}")
                    logger.info(f"   Target: {parsed['target']}")
                    logger.info(f"   Deal Type: {parsed['deal_type']}")
                    logger.info(f"   Date: {parsed['date_announced']}")
                    if parsed.get('total_deal_value_usd'):
                        logger.info(f"   Total Value: ${parsed['total_deal_value_usd']:,.0f}")

                    # Create Deal object
                    from decimal import Decimal
                    from deal_finder.models import FieldEvidence

                    deal = Deal(
                        date_announced=parsed["date_announced"],
                        target=company_canonicalizer.canonicalize(parsed["target"]),
                        acquirer=company_canonicalizer.canonicalize(parsed["acquirer"]),
                        stage=parsed["stage"],
                        therapeutic_area=parsed["therapeutic_area"],
                        asset_focus=parsed["asset_focus"],
                        deal_type_detailed=parsed["deal_type"],
                        source_url=parsed["url"],
                        needs_review=parsed["needs_review"],
                        upfront_value_usd=parsed["upfront_value_usd"],
                        contingent_payment_usd=parsed["contingent_payment_usd"],
                        total_deal_value_usd=parsed["total_deal_value_usd"],
                        upfront_pct_total=parsed["upfront_pct_total"],
                        geography=parsed["geography"],
                        detected_currency=parsed["currency"],
                        fx_rate=Decimal("1.0") if parsed["currency"] == "USD" else None,
                        fx_source="Perplexity",
                        evidence=FieldEvidence(
                            date_announced=parsed["evidence"],
                            target=parsed["evidence"],
                            acquirer=parsed["evidence"],
                        ),
                        inclusion_reason=f"Quick test extraction (confidence: {parsed['confidence']})",
                        timestamp_utc=datetime.utcnow().isoformat(),
                    )

                    # Save to Excel
                    logger.info("\n7. Saving to Excel...")
                    output_dir = Path(__file__).parent / "output"
                    output_dir.mkdir(exist_ok=True)
                    output_file = output_dir / f"quick_test_{uuid.uuid4().hex[:8]}.xlsx"

                    excel_writer = ExcelWriter()
                    excel_writer.write([deal], str(output_file))

                    logger.info(f"   ✓ Saved to: {output_file}")
                    logger.info("\n✅ Quick test complete!")
                    logger.info(f"\nOpen {output_file} to see the deal")

                    # Cleanup
                    web_client.close()
                    return 0

            # Reset for next batch
            fetched_articles = []

    # If we get here, no deals found in first 50 articles
    logger.warning("\n⚠ No deals found in first 50 articles")
    logger.info("This is expected - most articles are not deals")
    logger.info("Try running full pipeline to process more articles")

    web_client.close()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(quick_test())
    except KeyboardInterrupt:
        logger.info("\n\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"\n\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
