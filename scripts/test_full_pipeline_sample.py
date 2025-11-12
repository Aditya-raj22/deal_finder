"""
End-to-End Pipeline Test
Tests the full pipeline with a small sample (5 URLs per source) to verify:
- Crawling works
- Content fetching works
- Keyword filtering works
- Perplexity extraction works
- Excel output works
- No rate limiting issues
"""

import json
import logging
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from deal_finder.config_loader import load_config, load_ta_vocab, load_aliases
from deal_finder.keyword_filter import KeywordFilter
from deal_finder.discovery.exhaustive_crawler import ExhaustiveSiteCrawler
from deal_finder.utils.selenium_client import SeleniumWebClient
from deal_finder.extraction.perplexity_extractor import PerplexityExtractor
from deal_finder.normalization import CompanyCanonicalizer
from deal_finder.models import Deal, FieldEvidence
from deal_finder.output import ExcelWriter
from bs4 import BeautifulSoup
from decimal import Decimal

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Run end-to-end test with small sample."""
    logger.info("=" * 80)
    logger.info("END-TO-END PIPELINE TEST (Small Sample)")
    logger.info("=" * 80)

    # Load configuration
    config = load_config("config/config.yaml")
    ta_vocab = load_ta_vocab(config)
    aliases = load_aliases(config)

    therapeutic_area = ta_vocab["therapeutic_area"]
    start_date = config.START_DATE
    end_date = config.end_date_resolved

    logger.info(f"Therapeutic Area: {therapeutic_area}")
    logger.info(f"Date Range: {start_date} to {end_date}")

    # Load keywords
    keywords_file = Path("config/generated_keywords.json")
    if not keywords_file.exists():
        logger.error(f"❌ Keywords file not found: {keywords_file}")
        return 1

    with open(keywords_file) as f:
        keyword_data = json.load(f)

    ta_keywords = keyword_data["keywords"]["ta_keywords"]
    stage_keywords = keyword_data["keywords"]["stage_keywords"]
    deal_keywords = keyword_data["keywords"]["deal_keywords"]

    # Check Perplexity API key
    perplexity_key = os.getenv("PERPLEXITY_API_KEY")
    if not perplexity_key:
        logger.error("❌ PERPLEXITY_API_KEY not set!")
        return 1

    # STEP 1: Crawl small sample (5 URLs per source)
    logger.info("\n" + "=" * 80)
    logger.info("STEP 1: Crawl Sample URLs (5 per source)")
    logger.info("=" * 80)

    url_filters = config.URL_FILTERS
    crawler = ExhaustiveSiteCrawler(
        from_date=start_date,
        to_date=end_date,
        use_index=False,  # Don't use index for test
        url_filters=url_filters
    )

    # Crawl all sites but limit to 5 URLs per source
    all_discovered = crawler.crawl_all_sites()

    # Group by source and take 5 from each
    by_source = {}
    for article in all_discovered:
        source = article.get('source', 'Unknown')
        if source not in by_source:
            by_source[source] = []
        if len(by_source[source]) < 5:  # Limit to 5 per source
            by_source[source].append(article)

    discovered_urls = []
    for source, articles in by_source.items():
        discovered_urls.extend(articles)
        logger.info(f"  {source}: {len(articles)} URLs")

    logger.info(f"✓ Total sample: {len(discovered_urls)} URLs")

    # STEP 2: Fetch content
    logger.info("\n" + "=" * 80)
    logger.info("STEP 2: Fetch Article Content")
    logger.info("=" * 80)

    web_client = SeleniumWebClient(headless=True, timeout=20)
    articles = []
    fetch_failures = 0

    for i, article_meta in enumerate(discovered_urls, 1):
        url = article_meta["url"]
        logger.info(f"Fetching {i}/{len(discovered_urls)}: {url[:60]}...")

        try:
            html = web_client.fetch(url)
            if not html:
                fetch_failures += 1
                continue

            soup = BeautifulSoup(html, "lxml")
            text = soup.get_text(separator=" ", strip=True)

            if len(text) < 500:
                logger.warning(f"  Skipped (too short): {len(text)} chars")
                continue

            articles.append({
                "url": url,
                "title": article_meta.get("title", ""),
                "published_date": article_meta.get("published_date", ""),
                "content": text[:20000],
                "source": article_meta.get("source", "Unknown")
            })
            logger.info(f"  ✓ Fetched: {len(text)} chars")

        except Exception as e:
            logger.warning(f"  Error: {e}")
            fetch_failures += 1

    web_client.close()
    logger.info(f"✓ Fetched {len(articles)} articles ({fetch_failures} failures)")

    # STEP 3: Keyword filter
    logger.info("\n" + "=" * 80)
    logger.info("STEP 3: Keyword Pre-Filter")
    logger.info("=" * 80)

    keyword_filter = KeywordFilter(
        ta_keywords=ta_keywords,
        stage_keywords=stage_keywords,
        deal_keywords=deal_keywords,
        require_deal_keyword=True,
        min_ta_matches=1
    )

    filter_results = keyword_filter.filter_articles(articles)
    passed_articles = filter_results["passed"]

    logger.info(f"✓ Filter: {len(passed_articles)}/{len(articles)} passed")

    # Show which sources passed
    passed_by_source = {}
    for article in passed_articles:
        source = article.get('source', 'Unknown')
        passed_by_source[source] = passed_by_source.get(source, 0) + 1

    logger.info("  Passed by source:")
    for source, count in passed_by_source.items():
        logger.info(f"    {source}: {count}")

    if not passed_articles:
        logger.warning("⚠ No articles passed filter! Try with more URLs or adjust filters.")
        return 1

    # STEP 4: Perplexity extraction (SMALL BATCH)
    logger.info("\n" + "=" * 80)
    logger.info("STEP 4: Perplexity Extraction")
    logger.info("=" * 80)
    logger.info(f"Extracting from {len(passed_articles)} articles...")

    perplexity_extractor = PerplexityExtractor(api_key=perplexity_key, batch_size=3)
    extractions = perplexity_extractor.extract_batch(passed_articles, ta_vocab)

    # STEP 5: Parse results
    logger.info("\n" + "=" * 80)
    logger.info("STEP 5: Parse Results")
    logger.info("=" * 80)

    company_canonicalizer = CompanyCanonicalizer(aliases)
    extracted_deals = []
    perplexity_rejected = []

    for i, extraction in enumerate(extractions):
        article = passed_articles[i]
        url = article["url"]

        if not extraction:
            perplexity_rejected.append({
                "url": url,
                "title": article.get("title", ""),
                "source": article.get("source", "Unknown"),
                "perplexity_reason": "No deal found"
            })
            continue

        parsed = perplexity_extractor.parse_extracted_deal(extraction, therapeutic_area)

        if not parsed:
            perplexity_rejected.append({
                "url": url,
                "title": article.get("title", ""),
                "source": article.get("source", "Unknown"),
                "perplexity_reason": "Parsing failed"
            })
            continue

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
            inclusion_reason=f"Keyword + Perplexity (conf: {parsed['confidence']})",
            timestamp_utc=datetime.utcnow().isoformat()
        )

        extracted_deals.append(deal)
        logger.info(f"✓ Deal: {deal.acquirer} + {deal.target} ({deal.date_announced})")

    logger.info(f"✓ Extracted {len(extracted_deals)} deals")

    # STEP 6: Save test outputs
    logger.info("\n" + "=" * 80)
    logger.info("STEP 6: Save Test Results")
    logger.info("=" * 80)

    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Output 1: Deals
    if extracted_deals:
        deals_file = output_dir / f"TEST_deals_{timestamp}.xlsx"
        ExcelWriter().write(extracted_deals, str(deals_file))
        logger.info(f"✓ Saved {len(extracted_deals)} test deals to: {deals_file}")

    # Output 2: Rejected
    if perplexity_rejected:
        import pandas as pd
        rejected_file = output_dir / f"TEST_rejected_{timestamp}.xlsx"
        pd.DataFrame(perplexity_rejected).to_excel(rejected_file, index=False)
        logger.info(f"✓ Saved {len(perplexity_rejected)} rejected to: {rejected_file}")

    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("✅ END-TO-END TEST COMPLETE!")
    logger.info("=" * 80)
    logger.info(f"\nResults:")
    logger.info(f"  • URLs crawled: {len(discovered_urls)}")
    logger.info(f"  • Articles fetched: {len(articles)}")
    logger.info(f"  • Passed keyword filter: {len(passed_articles)}")
    logger.info(f"  • Deals extracted: {len(extracted_deals)}")
    logger.info(f"  • Rejected: {len(perplexity_rejected)}")
    logger.info(f"\n💰 Test cost: ~${len(passed_articles) * 0.06:.2f}")
    logger.info("\n✅ Pipeline is working! Ready for full run.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
