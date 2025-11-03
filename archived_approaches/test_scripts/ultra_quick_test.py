"""Ultra-quick test - Use known deal articles for fast validation."""

import logging
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def ultra_quick_test():
    """Ultra-quick test: Use known deal articles."""
    import os
    from bs4 import BeautifulSoup
    from deal_finder.config_loader import load_config, load_ta_vocab, load_aliases
    from deal_finder.extraction.perplexity_extractor import PerplexityExtractor
    from deal_finder.normalization import CompanyCanonicalizer
    from deal_finder.utils.selenium_client import SeleniumWebClient
    from deal_finder.models import Deal, FieldEvidence
    from deal_finder.output import ExcelWriter
    from decimal import Decimal
    import uuid

    logger.info("=" * 70)
    logger.info("ULTRA-QUICK TEST - Known Deal Articles (< 2 minutes)")
    logger.info("=" * 70)

    # Check Perplexity API key
    api_key = os.getenv("PERPLEXITY_API_KEY")
    if not api_key:
        logger.error("\n❌ PERPLEXITY_API_KEY not set!")
        logger.info("Set it with: export PERPLEXITY_API_KEY='pplx-...'")
        return 1

    logger.info(f"\n✓ API key found")

    # Known deal articles (these definitely contain deals)
    known_deals = [
        {
            "url": "https://www.fiercebiotech.com/biotech/pfizer-pays-67b-arena-pharmaceuticals",
            "title": "Pfizer pays $6.7B for Arena Pharmaceuticals",
            "expected": "Pfizer acquiring Arena Pharmaceuticals"
        },
        {
            "url": "https://www.fiercepharma.com/pharma/bristol-myers-squibb-buys-out-ifm-therapeutics-23b",
            "title": "Bristol Myers Squibb buys out IFM Therapeutics for $2.3B",
            "expected": "BMS acquiring IFM Therapeutics"
        },
        {
            "url": "https://www.fiercebiotech.com/biotech/gilead-licenses-arcus-cancer-drug-375m-upfront",
            "title": "Gilead licenses Arcus cancer drug for $375M upfront",
            "expected": "Gilead licensing from Arcus"
        }
    ]

    logger.info(f"\n1. Testing with {len(known_deals)} known deal articles")
    for i, deal_info in enumerate(known_deals, 1):
        logger.info(f"   {i}. {deal_info['expected']}")

    # Load config
    logger.info("\n2. Loading configuration...")
    config_path = Path(__file__).parent / "config" / "config.yaml"
    config = load_config(str(config_path))
    ta_vocab = load_ta_vocab(config)
    aliases = load_aliases(config)

    # Initialize components
    logger.info("\n3. Initializing components...")
    web_client = SeleniumWebClient(headless=True, timeout=20)
    perplexity_extractor = PerplexityExtractor(api_key=api_key, batch_size=3)
    company_canonicalizer = CompanyCanonicalizer(aliases)

    # Fetch articles
    logger.info("\n4. Fetching article content...")
    fetched_articles = []

    for i, deal_info in enumerate(known_deals, 1):
        url = deal_info["url"]
        logger.info(f"   [{i}/{len(known_deals)}] {url}")

        try:
            html = web_client.fetch(url)
            if not html:
                logger.warning(f"   ⚠ Failed to fetch")
                continue

            soup = BeautifulSoup(html, "lxml")
            text = soup.get_text(separator=" ", strip=True)

            if len(text) < 500:
                logger.warning(f"   ⚠ Content too short")
                continue

            fetched_articles.append({
                "url": url,
                "title": deal_info["title"],
                "content": text[:20000],
                "expected": deal_info["expected"]
            })

            logger.info(f"   ✓ Fetched ({len(text):,} chars)")

        except Exception as e:
            logger.warning(f"   ⚠ Error: {e}")
            continue

    if not fetched_articles:
        logger.error("\n❌ Failed to fetch any articles")
        web_client.close()
        return 1

    logger.info(f"\n   Successfully fetched {len(fetched_articles)}/{len(known_deals)} articles")

    # Extract deals using Perplexity
    logger.info("\n5. Extracting deals with Perplexity...")
    logger.info("   (This takes ~10-20 seconds per batch)")

    extractions = perplexity_extractor.extract_batch(fetched_articles, ta_vocab)
    logger.info(f"   ✓ Extraction complete")

    # Parse results
    logger.info("\n6. Parsing extraction results...")
    deals = []

    for i, extraction in enumerate(extractions):
        expected = fetched_articles[i].get("expected", "unknown")

        if not extraction:
            logger.warning(f"   [{i+1}] ✗ No extraction for: {expected}")
            continue

        parsed = perplexity_extractor.parse_extracted_deal(
            extraction,
            ta_vocab["therapeutic_area"]
        )

        if not parsed:
            logger.warning(f"   [{i+1}] ✗ Extraction filtered out: {expected}")
            logger.info(f"         Reason: TA match={extraction.get('therapeutic_area_match')}")
            continue

        logger.info(f"   [{i+1}] ✓ Deal extracted: {expected}")
        logger.info(f"         Acquirer: {parsed['acquirer']}")
        logger.info(f"         Target: {parsed['target']}")
        logger.info(f"         Type: {parsed['deal_type']}")
        logger.info(f"         Date: {parsed['date_announced']}")
        if parsed.get('total_deal_value_usd'):
            logger.info(f"         Value: ${parsed['total_deal_value_usd']:,.0f} USD")

        # Create Deal object
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
            inclusion_reason=f"Ultra-quick test (confidence: {parsed['confidence']})",
            timestamp_utc=datetime.utcnow().isoformat(),
        )

        deals.append(deal)

    # Save results
    if deals:
        logger.info(f"\n7. Saving {len(deals)} deal(s) to Excel...")
        output_dir = Path(__file__).parent / "output"
        output_dir.mkdir(exist_ok=True)
        output_file = output_dir / f"ultra_quick_test_{uuid.uuid4().hex[:8]}.xlsx"

        excel_writer = ExcelWriter()
        excel_writer.write(deals, str(output_file))

        logger.info(f"   ✓ Saved to: {output_file}")

        logger.info("\n" + "=" * 70)
        logger.info("✅ ULTRA-QUICK TEST COMPLETE!")
        logger.info("=" * 70)
        logger.info(f"\nResults:")
        logger.info(f"  • Processed: {len(fetched_articles)} articles")
        logger.info(f"  • Extracted: {len(deals)} deals")
        logger.info(f"  • Output: {output_file}")
        logger.info(f"\nOpen the Excel file to see the extracted deals!")

    else:
        logger.warning("\n⚠ No deals extracted")
        logger.info("Possible reasons:")
        logger.info("  • Articles don't match therapeutic area filter")
        logger.info("  • Extraction confidence too low")
        logger.info("  • Try adjusting ta_vocab includes/excludes")

    # Cleanup
    web_client.close()
    return 0 if deals else 1


if __name__ == "__main__":
    try:
        sys.exit(ultra_quick_test())
    except KeyboardInterrupt:
        logger.info("\n\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"\n\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
