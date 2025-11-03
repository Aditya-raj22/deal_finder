"""
Test Perplexity Extraction

Quick test to verify:
1. Perplexity API works
2. Extraction logic works
3. Excel generation works

Uses a few sample articles to test the pipeline.
"""

import json
import logging
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path
from decimal import Decimal

sys.path.insert(0, str(Path(__file__).parent))

from deal_finder.config_loader import load_config, load_ta_vocab, load_aliases
from deal_finder.extraction.perplexity_extractor import PerplexityExtractor
from deal_finder.normalization import CompanyCanonicalizer
from deal_finder.models import Deal, FieldEvidence
from deal_finder.output import ExcelWriter

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Sample articles for testing (immunology/inflammation deals)
SAMPLE_ARTICLES = [
    {
        "url": "https://www.fiercebiotech.com/biotech/pfizer-arena-deal-example",
        "title": "Pfizer buys Arena Pharmaceuticals for $6.7B to boost immunology pipeline",
        "content": """On December 13, 2021, Pfizer announced it has agreed to acquire Arena Pharmaceuticals
        for $6.7 billion in cash. The deal gives Pfizer access to Arena's etrasimod, a preclinical S1P
        receptor modulator for inflammatory bowel disease. Pfizer will pay $100 per share in cash for Arena.
        The acquisition is expected to close in the first half of 2022. Arena is developing etrasimod for
        ulcerative colitis and Crohn's disease, both inflammatory bowel diseases. The drug candidate is in
        preclinical development targeting immune-mediated conditions and has shown promising efficacy in
        reducing inflammation in animal models.""",
        "published_date": "2021-12-13"
    },
    {
        "url": "https://www.fiercebiotech.com/partnering/abbvie-license-deal",
        "title": "AbbVie licenses rheumatoid arthritis drug candidate for $500M",
        "content": """On March 15, 2024, AbbVie announced it has signed a licensing agreement with a biotech
        partner for a preclinical rheumatoid arthritis drug candidate. The deal is worth up to $500 million
        including milestones. AbbVie will pay $50 million upfront and up to $450 million in development and
        commercial milestones. The drug is a novel JAK inhibitor targeting inflammation in autoimmune diseases.
        The candidate is currently in preclinical development and expected to enter Phase 1 trials next year
        for rheumatoid arthritis and potentially other inflammatory conditions.""",
        "published_date": "2024-03-15"
    },
    {
        "url": "https://www.fiercebiotech.com/biotech/sanofi-acquisition-immunology",
        "title": "Sanofi acquires Translate Bio to expand mRNA vaccine capabilities",
        "content": """On August 3, 2021, Sanofi announced it will acquire Translate Bio for $3.2 billion.
        The acquisition expands Sanofi's mRNA platform for vaccines and therapeutics, including potential
        treatments for autoimmune diseases. Sanofi will pay $38 per share in cash. The deal closed in Q3 2021.
        Translate Bio's mRNA technology could be applied to inflammatory and immune-mediated diseases beyond
        infectious disease vaccines.""",
        "published_date": "2021-08-03"
    }
]


def main():
    """Test Perplexity extraction and Excel generation."""
    import argparse

    parser = argparse.ArgumentParser(description="Test Perplexity Extraction")
    parser.add_argument(
        "--config",
        default="config/config.yaml",
        help="Path to config file"
    )

    args = parser.parse_args()

    logger.info("=" * 80)
    logger.info("TEST: Perplexity Extraction + Excel Generation")
    logger.info("=" * 80)

    # Load configuration
    config = load_config(args.config)
    ta_vocab = load_ta_vocab(config)
    aliases = load_aliases(config)

    therapeutic_area = ta_vocab["therapeutic_area"]
    logger.info(f"Therapeutic Area: {therapeutic_area}")

    # Check Perplexity API key
    perplexity_key = os.getenv("PERPLEXITY_API_KEY")
    if not perplexity_key:
        # Try loading from .env.example
        env_file = Path(__file__).parent / ".env.example"
        if env_file.exists():
            with open(env_file) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("PERPLEXITY_API_KEY="):
                        perplexity_key = line.split("=", 1)[1]
                        os.environ["PERPLEXITY_API_KEY"] = perplexity_key
                        break

    if not perplexity_key:
        logger.error("❌ PERPLEXITY_API_KEY not set!")
        return 1

    logger.info("✓ API key found")

    # TEST 1: Perplexity Extraction
    logger.info("\n" + "=" * 80)
    logger.info("TEST 1: Perplexity Extraction (3 sample articles)")
    logger.info("=" * 80)

    perplexity_extractor = PerplexityExtractor(api_key=perplexity_key, batch_size=3)
    extractions = perplexity_extractor.extract_batch(SAMPLE_ARTICLES, ta_vocab)

    logger.info(f"✓ Extracted {len(extractions)} results")

    # TEST 2: Parse results
    logger.info("\n" + "=" * 80)
    logger.info("TEST 2: Parse Extracted Deals")
    logger.info("=" * 80)

    company_canonicalizer = CompanyCanonicalizer(aliases)
    extracted_deals = []

    for i, extraction in enumerate(extractions):
        article = SAMPLE_ARTICLES[i]
        url = article["url"]

        if not extraction:
            logger.info(f"  ❌ Article {i+1}: No deal found")
            continue

        # DEBUG: Show what Perplexity returned
        logger.info(f"\n  DEBUG Article {i+1} extraction:")
        if isinstance(extraction, str):
            logger.info(f"    Raw string: {extraction[:500]}...")
        else:
            logger.info(f"    Type: {type(extraction)}")
            logger.info(f"    Content: {extraction}")

        parsed = perplexity_extractor.parse_extracted_deal(extraction, therapeutic_area)

        if not parsed:
            logger.info(f"  ❌ Article {i+1}: Parsing failed")
            continue

        logger.info(f"  ✓ Article {i+1}: {parsed['acquirer']} + {parsed['target']}")

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
                acquirer=parsed["evidence"]
            ),
            inclusion_reason=f"Test extraction (conf: {parsed['confidence']})",
            timestamp_utc=datetime.utcnow().isoformat()
        )

        extracted_deals.append(deal)

    logger.info(f"\n✓ Parsed {len(extracted_deals)} deals")

    # TEST 3: Excel Generation
    logger.info("\n" + "=" * 80)
    logger.info("TEST 3: Generate Excel Output")
    logger.info("=" * 80)

    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)

    if extracted_deals:
        test_id = uuid.uuid4().hex[:8]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        deals_file = output_dir / f"TEST_deals_{timestamp}_{test_id}.xlsx"

        ExcelWriter().write(extracted_deals, str(deals_file))
        logger.info(f"✓ Saved {len(extracted_deals)} deals to: {deals_file}")
        logger.info(f"\n  Open file: {deals_file}")
    else:
        logger.warning("⚠ No deals to save")

    # SUMMARY
    logger.info("\n" + "=" * 80)
    logger.info("✅ TEST COMPLETE!")
    logger.info("=" * 80)
    logger.info(f"\nResults:")
    logger.info(f"  • Articles tested: {len(SAMPLE_ARTICLES)}")
    logger.info(f"  • Deals extracted: {len(extracted_deals)}")
    logger.info(f"  • Success rate: {len(extracted_deals)}/{len(SAMPLE_ARTICLES)}")

    if len(extracted_deals) > 0:
        logger.info(f"\n✓ Perplexity extraction working!")
        logger.info(f"✓ Excel generation working!")
        logger.info(f"\nYou can now run the full pipeline:")
        logger.info(f"  python step2_run_pipeline.py")
    else:
        logger.warning(f"\n⚠ No deals extracted - check Perplexity prompts")

    return 0


if __name__ == "__main__":
    sys.exit(main())
